"""Local, versioned shot/transcript/sample evidence; no cloud visual inference."""
import json
import math
import re
import sqlite3
from pathlib import Path
from .common import FileLock, PipelineError, digest, file_hash, read_json, reject_alias, utcnow
from .media import probe, stream_duration, run, ffmpeg_args, tool
from .sampling import sample_video


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    return db


def build_index(source, index_path, *, transcript=None, samples=None, threshold=.3):
    source, index_path = Path(source).resolve(), Path(index_path).resolve()
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise PipelineError('scene_threshold', 'threshold', 'Use a finite scene threshold in (0, 1].')
    protected = [source] + ([Path(transcript).resolve()] if transcript else []) + ([Path(samples).resolve()] if samples else [])
    reject_alias(index_path, protected)
    source_hash = file_hash(source)
    asset_id = 'sha256:' + source_hash
    transcript_path = Path(transcript).resolve() if transcript else None
    supplied_samples = Path(samples).resolve() if samples else None
    settings = {'analysis_version': 1, 'threshold': threshold,
        'transcript_sha256': file_hash(transcript_path) if transcript_path else None,
        'sample_index_sha256': file_hash(supplied_samples) if supplied_samples else None,
        'ffmpeg': run([tool('ffmpeg'), '-version']).stdout.splitlines()[0]}
    settings_hash = digest(settings)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(index_path.with_name(index_path.name + '.lock'), timeout=30):
        db = connect(index_path)
        try:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS schema_info (version INTEGER NOT NULL)')
                version = db.execute('SELECT version FROM schema_info').fetchone()
                if version is not None and version[0] != 1:
                    raise PipelineError('index_version', 'index', 'Unsupported footage index version.')
                if version is None:
                    db.execute('INSERT INTO schema_info VALUES (1)')
                db.execute('''CREATE TABLE IF NOT EXISTS assets (asset_id TEXT PRIMARY KEY, source TEXT UNIQUE,
                    sha256 TEXT, settings_hash TEXT, data TEXT, indexed_at TEXT)''')
            prior = db.execute('SELECT data FROM assets WHERE asset_id=? AND source=? AND settings_hash=?',
                               (asset_id, str(source), settings_hash)).fetchone()
            if prior:
                return {'version': 1, 'status': 'cached', 'asset_id': asset_id, 'index': str(index_path)}
            info = probe(source)
            video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
            audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
            primary = video or audio
            duration = stream_duration(primary, info)
            if duration is None:
                raise PipelineError('unknown_duration', 'source', 'Cannot index an asset without a usable duration.')
            samples_data, boundaries = None, [0.0]
            if video:
                if supplied_samples:
                    samples_data = read_json(supplied_samples)
                    if samples_data.get('version') != 2 or samples_data.get('source_sha256') != source_hash:
                        raise PipelineError('stale_samples', 'samples', 'Sample evidence does not match this source identity.')
                    samples_root = supplied_samples.parent
                else:
                    samples_root = index_path.parent / ('footage-samples-' + source_hash[:16])
                    previous_index = samples_root / 'index.json'
                    if previous_index.is_file() and read_json(previous_index).get('source_sha256') == source_hash:
                        samples_data = read_json(previous_index)
                    else:
                        samples_data = sample_video(source, samples_root, count=8)
                result = run(ffmpeg_args() + ['-loglevel', 'info', '-i', str(source), '-an',
                    '-vf', f'setpts=PTS-STARTPTS,select=gt(scene\\,{threshold}),showinfo', '-fps_mode', 'vfr', '-f', 'null', '-'])
                detected = [float(v) for v in re.findall(r'\bpts_time:([-+0-9.eE]+)', result.stderr)]
                boundaries += sorted({value for value in detected if 0 < value < duration})
                for frame in samples_data['frames']:
                    frame['frame'] = str((samples_root / frame['frame']).resolve())
                samples_data['sheets'] = [str((samples_root / p).resolve()) for p in samples_data['sheets']]
            segments, transcript_status = [], 'missing_transcript'
            if transcript_path:
                evidence = read_json(transcript_path)
                transcript_status = evidence.get('status', 'complete')
                if transcript_status == 'complete':
                    for segment in evidence.get('segments', []):
                        start, end = segment.get('start'), segment.get('end')
                        if any(not isinstance(n, (int, float)) or not math.isfinite(n) for n in (start, end)) or not 0 <= start < end <= duration + .1:
                            raise PipelineError('transcript_range', 'segments', 'Transcript segment is outside this source.')
                        if not isinstance(segment.get('text'), str):
                            raise PipelineError('transcript_text', 'segments.text', 'Transcript text must be a string.')
                        segments.append(segment)
            if not audio:
                if segments:
                    raise PipelineError('silent_transcript', 'transcript', 'Cannot attach speech evidence to a source without audio.')
                transcript_status = 'no_audio'
            shots = [{'shot_id': f'{asset_id}:shot:{i}', 'start': start, 'end': end,
                      'method': 'ffmpeg-scene-score', 'threshold': threshold}
                     for i, (start, end) in enumerate(zip(boundaries, boundaries[1:] + [duration]))] if video else []
            data = {'asset_id': asset_id, 'source': str(source), 'source_sha256': source_hash,
                'duration': duration, 'has_video': bool(video), 'has_audio': bool(audio), 'settings': settings,
                'shots': shots, 'samples': samples_data['frames'] if samples_data else [],
                'contact_sheets': samples_data['sheets'] if samples_data else [], 'segments': segments,
                'transcript_status': transcript_status, 'evidence': 'observed-timestamps-and-transcript; no inferred scene descriptions'}
            if file_hash(source) != source_hash:
                raise PipelineError('source_changed', 'source', 'Asset changed during indexing; no entry was published.')
            with db:
                db.execute('DELETE FROM assets WHERE source=? OR asset_id=?', (str(source), asset_id))
                db.execute('INSERT INTO assets VALUES (?,?,?,?,?,?)',
                    (asset_id, str(source), source_hash, settings_hash, json.dumps(data, ensure_ascii=False), utcnow()))
            return {'version': 1, 'status': 'indexed', 'asset_id': asset_id, 'index': str(index_path),
                    'shots': len(shots), 'segments': len(segments), 'samples': len(data['samples'])}
        finally:
            db.close()


def query_index(index_path, *, text='', start=None, end=None, kind='transcript', asset_id=None, limit=20, offset=0):
    if kind not in ('transcript', 'shot', 'sample') or not 1 <= limit <= 100 or offset < 0:
        raise PipelineError('query_schema', 'query', 'Use transcript/shot/sample, limit 1..100, and nonnegative offset.')
    for name, value in [('start', start), ('end', end)]:
        if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
            raise PipelineError('query_range', name, 'Time bounds must be finite and nonnegative.')
    if start is not None and end is not None and end <= start:
        raise PipelineError('query_range', 'end', 'End must follow start.')
    path = Path(index_path).resolve()
    if not path.is_file():
        raise PipelineError('missing_index', 'index', 'Footage index does not exist.')
    db = connect(path)
    try:
        version = db.execute('SELECT version FROM schema_info').fetchone()
        if not version or version[0] != 1:
            raise PipelineError('index_version', 'index', 'Unsupported index version.')
        rows = db.execute('SELECT * FROM assets' + (' WHERE asset_id=?' if asset_id else '') + ' ORDER BY asset_id', [asset_id] if asset_id else []).fetchall()
        matches, stale, skipped = [], [], 0
        for row in rows:
            source = Path(row['source'])
            if not source.is_file() or file_hash(source) != row['sha256']:
                stale.append(row['asset_id'])
                continue
            data = json.loads(row['data'])
            records = data[{'transcript': 'segments', 'shot': 'shots', 'sample': 'samples'}[kind]]
            for item in records:
                a = item.get('start', item.get('timestamp', 0))
                b = item.get('end', a + .000001)
                if (start is not None and b <= start) or (end is not None and a >= end):
                    continue
                if text and text.casefold() not in item.get('text', '').casefold():
                    continue
                if skipped < offset:
                    skipped += 1
                    continue
                nearest = min(data['samples'], key=lambda f: abs(f['timestamp'] - a), default=None)
                shot = next((s for s in data['shots'] if s['start'] <= a < s['end']), None)
                result = {'asset_id': row['asset_id'], 'source': row['source'], 'source_range': {'in': a, 'duration': b-a},
                          'kind': kind, 'evidence': item, 'nearby_sample': nearest, 'shot': shot,
                          'contact_sheets': data['contact_sheets'], 'transcript_status': data['transcript_status']}
                if nearest and not Path(nearest['frame']).is_file():
                    result['nearby_sample'] = None
                    result['warning'] = 'Sample file is missing; rebuild sampling evidence.'
                matches.append(result)
                if len(matches) > limit:
                    return {'version': 1, 'items': matches[:limit], 'next_offset': offset + limit, 'stale_assets': stale}
        return {'version': 1, 'items': matches, 'next_offset': None, 'stale_assets': stale}
    finally:
        db.close()
