"""Durable ingest lifecycle and provenance-preserving resume."""
from __future__ import annotations
import os
import shutil
import stat
import time
from pathlib import Path
from .common import (FileLock, PipelineError, read_json, write_json, atomic_write,
                     digest, file_hash, utcnow, output_transaction, same_file)
from .media import probe, stream_duration, run, ffmpeg_args, check_cancel, Cancelled
from .state import JobStore
from .sampling import sample_video


def source_identity(source):
    source = Path(source).resolve()
    if not source.is_file():
        raise PipelineError('missing_source', str(source), 'Source is not a regular file.')
    info = source.stat()
    identity = {'path': os.path.normcase(str(source)), 'size': info.st_size, 'mtime_ns': info.st_mtime_ns}
    return digest(identity), identity


def readonly(path):
    path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def clone_verified(source, clone, manifest, cancel=None):
    """Source remains untouched; only an owned temporary sibling is writable."""
    expected = manifest.get('sha256')
    if clone.exists():
        actual = file_hash(clone)
        if expected and actual.lower() == expected.lower():
            readonly(clone)
            return actual
        if not expected and source is not None and actual == file_hash(source):
            readonly(clone)
            return actual
        raise PipelineError('clone_mismatch', 'clone_path', 'Existing clone does not match trustworthy evidence.',
                            'Preserve this workspace for investigation; restore its recorded clone before retrying.')
    if source is None or not source.is_file():
        raise PipelineError('missing_clone', 'clone_path', 'Clone and recoverable original are unavailable.')
    _, before = source_identity(source)
    if manifest.get('original_size') is not None and before['size'] != manifest['original_size']:
        raise PipelineError('changed_source', 'original_path', 'Original size changed since the job was allocated.')
    clone.parent.mkdir(parents=True, exist_ok=True)
    # A fixed per-job staging name makes interrupted-copy recovery explicit.
    staging = clone.with_name('.' + clone.name + '.copying')
    if same_file(staging, source):
        raise PipelineError('copy_alias', 'clone_path', 'Copy staging path aliases the source.')
    staging.unlink(missing_ok=True)
    try:
        import hashlib
        checksum = hashlib.sha256()
        with source.open('rb') as src, staging.open('xb') as dst:
            while block := src.read(4 * 1024 * 1024):
                check_cancel(cancel)
                dst.write(block)
                checksum.update(block)
            dst.flush()
            os.fsync(dst.fileno())
        value = checksum.hexdigest()
        if source_identity(source)[1] != before or file_hash(staging) != value or file_hash(source) != value:
            raise PipelineError('changed_source', 'original_path', 'Source changed during copy or clone verification failed.')
        if expected and expected.lower() != value:
            raise PipelineError('clone_mismatch', 'sha256', 'Original no longer matches the historical source hash.')
        check_cancel(cancel)
        os.replace(staging, clone)
        readonly(clone)
        return value
    finally:
        staging.unlink(missing_ok=True)


def recorded_clone(job, manifest):
    if manifest.get('clone_path'):
        clone = (job / manifest['clone_path']).resolve()
    else:
        choices = [p for p in (job / 'source').glob('*') if p.is_file() and not p.name.endswith('.copying')]
        if len(choices) != 1:
            raise PipelineError('ambiguous_clone', 'clone_path', 'Legacy resume requires exactly one source file or a recorded clone path.')
        clone = choices[0].resolve()
    if not clone.is_relative_to((job / 'source').resolve()):
        raise PipelineError('clone_outside_job', 'clone_path', 'Recorded clone must be inside this job source directory.')
    return clone


def verify_resume(job, manifest, original_override=None):
    clone = recorded_clone(job, manifest)
    if not clone.is_file():
        raise PipelineError('missing_clone', 'clone_path', 'Recorded clone is missing; do not choose another file silently.')
    original_value = original_override or manifest.get('original_path')
    original = Path(original_value).resolve() if original_value else None
    if original and same_file(clone, original):
        raise PipelineError('clone_alias', 'original_path', 'Original and clone must be separate files.')
    clone_hash = file_hash(clone)
    expected = manifest.get('sha256')
    verified, evidence = False, 'unverified'
    if expected:
        if clone_hash.lower() != expected.lower():
            raise PipelineError('clone_mismatch', 'clone_path', 'Clone does not match the recorded full SHA-256.')
        verified, evidence = True, 'recorded-full-sha256'
    if original and original.is_file():
        current_original_hash = file_hash(original)
        if current_original_hash != clone_hash:
            # A historical verified clone is still valid when the old pathname has
            # since been reused, unless the caller explicitly requests comparison.
            if original_override or not verified:
                raise PipelineError('clone_mismatch', 'original_path', 'Available original does not match the clone.')
            manifest['original_current_status'] = 'changed-since-ingest'
        else:
            verified, evidence = True, 'original-full-sha256'
            if not manifest.get('original_path'):
                manifest['original_path'] = str(original)
            manifest.setdefault('original_size', original.stat().st_size)
            if not manifest.get('sha256'):
                manifest['sha256'] = clone_hash
    readonly(clone)
    manifest.setdefault('verification_history', []).append({
        'at': utcnow(), 'verified': verified, 'evidence': evidence, 'clone_sha256': clone_hash})
    manifest.update(clone_path=str(clone), clone_verified=verified,
        clone_verification_mode='full-sha256' if verified else 'unverified', clone_sha256=clone_hash,
        resumed_at=utcnow(), original_modified=False)
    return clone


def prepare_job(job, clone, config, stage, cancel=None):
    analysis = job / 'analysis'
    for name in ('analysis', 'edit', 'output'):
        (job / name).mkdir(parents=True, exist_ok=True)
    stage('probe')
    info = probe(clone)
    write_json(analysis / 'probe.json', info)
    check_cancel(cancel)
    audio = [s for s in info['streams'] if s['codec_type'] == 'audio']
    video = [s for s in info['streams'] if s['codec_type'] == 'video']
    if audio:
        stage('transcription-audio')
        voice = analysis / 'voiceover.wav'
        with output_transaction(voice, [clone]) as temp:
            run(ffmpeg_args() + ['-i', str(clone), '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(temp)], cancel=cancel)
            derivative = probe(temp)
            if not any(s['codec_type'] == 'audio' for s in derivative['streams']):
                raise PipelineError('missing_audio', 'analysis.voiceover', 'Transcription derivative has no audio.')
        write_json(analysis / 'voiceover.provenance.json', {'version': 1, 'purpose': 'transcription-only',
            'delivery_audio': str(clone), 'sample_rate': 16000, 'channels': 1})
    if video:
        stage('sampling')
        samples = sample_video(clone, analysis / 'samples', count=config.get('contact_sheet_frames', 16), cancel=cancel)
        with output_transaction(analysis / 'contact-sheet.jpg', [clone]) as temp:
            shutil.copyfile(analysis / 'samples' / samples['sheets'][0], temp)
    transcript = analysis / 'transcript.json'
    if not transcript.exists():
        write_json(transcript, {'version': 1, 'status': 'awaiting_transcription' if audio else 'no_audio', 'segments': []})
    timeline = job / 'edit' / 'timeline.json'
    if video and not timeline.exists():
        duration = stream_duration(video[0], info)
        from .timeline import frame_count, rate
        fps = rate(video[0].get('avg_frame_rate', '30/1'))
        # Floor the initial full-source clip so no rounded frame exceeds EOF.
        frames = int(duration * float(fps))
        if frames < 1:
            raise PipelineError('empty_video', 'source', 'Video is shorter than one usable frame.')
        write_json(timeline, {'version': 1, 'revision': 0,
            'video': {'width': 1920, 'height': 1080, 'fps': str(fps)},
            'clips': [{'id': 'clip-0001', 'source': '../source/' + clone.name,
                'duration': float(frames / fps), 'audio': {'mode': 'preserve'}}],
            'output': '../output/final.mp4'})
    stage('prepared')
    check_cancel(cancel)
    return info


def run_job(store, row, config, *, source=None, resume=False, original_override=None, force=False, cancel_external=None):
    job = Path(row['job_path'])
    identity_lock = digest({'original': os.path.normcase(row['original_path'])}) if row.get('original_path') else row['id']
    with FileLock(store.state / 'source-locks' / (identity_lock + '.lock'), timeout=30):
        with FileLock(job.with_name('.' + job.name + '.job.lock'), timeout=30):
            row = store.get(row['id'])
            if row['status'] == 'ready' and not resume and not force:
                if (job / 'READY.txt').is_file() and (job / 'manifest.json').is_file() and (job / 'analysis/probe.json').is_file():
                    return row
                return store.update(row['id'], status='stale', stage='missing-artifact',
                    error={'code': 'missing_artifact', 'message': 'Prepared job is missing artifacts; retry explicitly.'})
            if not force and (row['status'] in ('cancelled', 'cancel_requested', 'quarantined', 'stale') or row['retry_at'] > time.time()):
                return row
            maximum = config.get('max_attempts', 3)
            attempts = (0 if force else row['attempts']) + 1
            if attempts > maximum:
                return store.update(row['id'], status='quarantined', stage='retry-limit')
            job.mkdir(parents=True, exist_ok=True)
            (job / 'READY.txt').unlink(missing_ok=True)
            store.update(row['id'], status='processing', stage='starting', attempts=attempts,
                         retry_at=0, cancel_requested=0 if force else row['cancel_requested'], error=None)
            cancel = lambda: bool(store.get(row['id'])['cancel_requested']) or bool(cancel_external and cancel_external())
            stage = lambda value: store.update(row['id'], stage=value)
            manifest_path = job / 'manifest.json'
            try:
                check_cancel(cancel)
                if manifest_path.exists():
                    manifest = read_json(manifest_path)
                else:
                    original = source or (Path(row['original_path']) if row['original_path'] else None)
                    manifest = {'version': 2, 'job_id': row['id'], 'created_at': row['created_at'],
                        'original_path': str(original) if original else None, 'original_modified': False,
                        'clone_verified': False, 'verification_history': []}
                    if original is not None:
                        _, identity = source_identity(original)
                        manifest.update(original_size=identity['size'], original_mtime_ns=identity['mtime_ns'],
                            clone_path=str(job / 'source' / original.name))
                    write_json(manifest_path, manifest)
                if resume:
                    stage('verification')
                    clone = verify_resume(job, manifest, original_override)
                else:
                    source = source or Path(row['original_path'])
                    if source_identity(source)[0] != row['source_key']:
                        raise PipelineError('changed_source', 'source', 'Original identity changed after job allocation.')
                    clone = recorded_clone(job, manifest)
                    stage('copy-and-verify')
                    checksum = clone_verified(source, clone, manifest, cancel)
                    if not manifest.get('sha256'):
                        manifest['sha256'] = checksum
                    manifest.update(clone_path=str(clone), clone_sha256=checksum, clone_verified=True,
                                    clone_verification_mode='full-sha256', original_modified=False)
                    manifest.setdefault('verification_history', []).append({'at': utcnow(), 'verified': True,
                        'evidence': 'copy-and-full-sha256' if not manifest.get('prepared_at') else 'recorded-full-sha256',
                        'clone_sha256': checksum})
                write_json(manifest_path, manifest)
                prepare_job(job, clone, config, stage, cancel)
                manifest['prepared_at'] = utcnow()
                manifest['preparation_status'] = 'complete'
                write_json(manifest_path, manifest)
                check_cancel(cancel)
                return store.finish_ready(row['id'], manifest['prepared_at'])
            except (Exception, KeyboardInterrupt) as exc:
                (job / 'READY.txt').unlink(missing_ok=True)
                error = exc.as_dict() if isinstance(exc, PipelineError) else {'code': 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'preparation_failed', 'message': str(exc)}
                cancelled = isinstance(exc, (Cancelled, KeyboardInterrupt))
                status = 'cancelled' if cancelled else 'quarantined' if attempts >= maximum else 'failed'
                store.update(row['id'], status=status, error=error,
                    retry_at=0 if cancelled else time.time() + min(config.get('retry_base_seconds', 30) * 2 ** (attempts - 1), 3600))
                if isinstance(exc, KeyboardInterrupt):
                    raise
                return store.get(row['id'])


def ingest(root, source, config, *, force=False, cancel=None):
    source = Path(source).resolve()
    key, identity = source_identity(source)
    if source.is_relative_to((Path(root).resolve() / 'jobs')):
        raise PipelineError('recursive_ingest', 'source', 'Do not ingest pipeline job artifacts as new inbox sources.')
    if time.time() - source.stat().st_mtime < config.get('stable_seconds', 10):
        raise PipelineError('source_changing', 'source', 'Source has not reached the configured stability interval.')
    store = JobStore(root)
    # Allocation itself is unique and transactional; no media is copied before it.
    row = store.reserve(key, source)
    return run_job(store, row, config, source=source, force=force, cancel_external=cancel)


def resume_job(root, job, config, original=None):
    job = Path(job).resolve()
    manifest = read_json(job / 'manifest.json') if (job / 'manifest.json').is_file() else {}
    store = JobStore(root)
    try:
        row = store.get(str(job))
    except PipelineError:
        original_path = original or manifest.get('original_path')
        key = digest({'resume_job': str(job)})
        if original_path and Path(original_path).is_file():
            key = source_identity(Path(original_path))[0]
        row = store.reserve(key, original_path, job=job)
        if Path(row['job_path']) != job:
            raise PipelineError('source_owned', 'job', 'This original is already owned by a different registered workspace.', 'Resume the registered job or recover the state deliberately.')
    return run_job(store, row, config, resume=True, original_override=original, force=True)


def retry_job(root, identifier, config):
    store = JobStore(root)
    row = store.get(identifier)
    manifest_path = Path(row['job_path']) / 'manifest.json'
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        clone_path = manifest.get('clone_path')
        if clone_path and (Path(row['job_path']) / clone_path).is_file():
            return run_job(store, row, config, resume=True, force=True)
    return run_job(store, row, config, force=True)


def quarantine_job(root, identifier):
    store = JobStore(root)
    row = store.get(identifier)
    if row['status'] in ('processing', 'cancel_requested'):
        raise PipelineError('busy', 'job', 'Cancel the running job before quarantining it.')
    (Path(row['job_path']) / 'READY.txt').unlink(missing_ok=True)
    return store.update(row['id'], status='quarantined', stage='manual-quarantine')
