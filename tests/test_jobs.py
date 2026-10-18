"""Durable ingest/resume regressions against real synthetic media and processes."""
import concurrent.futures
import copy
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'examples')]
from generate_fixtures import generate
from pipeline.common import PipelineError, file_hash, read_json, write_json
from pipeline.jobs import ingest, resume_job, retry_job, source_identity
from pipeline.state import JobStore
from pipeline.operations import watch, doctor


class JobIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = tempfile.TemporaryDirectory(prefix='job-fixtures-')
        cls.media = generate(Path(cls.fixtures.name))

    @classmethod
    def tearDownClass(cls):
        cls.fixtures.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='job-case-')
        self.root = Path(self.temp.name)
        self.config = {'inbox_paths': [str(self.root / 'inbox')], 'extensions': ['.mkv', '.wav'],
            'stable_seconds': 0, 'poll_seconds': .05, 'contact_sheet_frames': 2,
            'max_attempts': 3, 'retry_base_seconds': .01}
        (self.root / 'inbox').mkdir()
        self.source = self.root / 'inbox' / 'source.mkv'
        shutil.copyfile(self.media / 'red.mkv', self.source)
        self.hash = file_hash(self.source)
        self.config_path = self.root / 'config.json'
        write_json(self.config_path, self.config)

    def tearDown(self):
        # Windows refuses to remove read-only cloned files; these are owned fixtures.
        for path in self.root.rglob('*'):
            if path.is_file():
                path.chmod(path.stat().st_mode | stat.S_IWUSR)
        self.temp.cleanup()

    def invoke(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/pipeline.py'), '--root', str(self.root),
            '--config', str(self.config_path), *map(str, arguments)], capture_output=True, text=True, encoding='utf-8', timeout=90)

    def test_ingest_ready_repeat_and_generated_timeline_contract(self):
        row = ingest(self.root, self.source, self.config)
        self.assertEqual(row['status'], 'ready', row['error'])
        job = Path(row['job_path'])
        manifest = read_json(job / 'manifest.json')
        self.assertEqual(manifest['sha256'], self.hash)
        self.assertEqual(manifest['clone_verification_mode'], 'full-sha256')
        self.assertFalse(Path(manifest['clone_path']).stat().st_mode & stat.S_IWUSR)
        again = ingest(self.root, self.source, self.config)
        self.assertEqual(row['id'], again['id'])
        self.assertEqual(again['attempts'], 1)
        self.assertEqual(len(JobStore(self.root).list()), 1)
        self.assertEqual(JobStore(self.root).latest_ready()['id'], row['id'])
        from pipeline.timeline import load_timeline
        self.assertGreater(load_timeline(job / 'edit/timeline.json', media=True).duration, 0)
        self.assertEqual(file_hash(self.source), self.hash)

    def test_analysis_failure_retry_reuses_clone_and_quarantines(self):
        with patch('pipeline.jobs.prepare_job', side_effect=PipelineError('injected_analysis', 'test', 'failure')):
            first = ingest(self.root, self.source, self.config)
            clone = Path(read_json(Path(first['job_path']) / 'manifest.json')['clone_path'])
            identity = (clone.stat().st_ino, clone.stat().st_mtime_ns)
            for _ in range(5):
                JobStore(self.root).update(first['id'], retry_at=0)
                row = ingest(self.root, self.source, self.config)
            self.assertEqual(row['status'], 'quarantined')
            self.assertEqual(row['attempts'], 3)
            self.assertEqual(len(JobStore(self.root).list()), 1)
            self.assertEqual(identity, (clone.stat().st_ino, clone.stat().st_mtime_ns))
            self.assertFalse((Path(row['job_path']) / 'READY.txt').exists())
        retried = retry_job(self.root, row['id'], self.config)
        self.assertEqual(retried['status'], 'ready', retried['error'])
        self.assertEqual(identity, (clone.stat().st_ino, clone.stat().st_mtime_ns))
        self.assertEqual(file_hash(self.source), self.hash)

    def test_interrupted_copy_recovery_owns_one_workspace(self):
        store = JobStore(self.root)
        key, identity = source_identity(self.source)
        row = store.reserve(key, self.source)
        job = Path(row['job_path'])
        clone = job / 'source' / self.source.name
        clone.parent.mkdir(parents=True)
        partial = clone.with_name('.' + clone.name + '.copying')
        partial.write_bytes(b'interrupted-copy')
        write_json(job / 'manifest.json', {'version': 2, 'job_id': row['id'], 'created_at': row['created_at'],
            'original_path': str(self.source), 'original_size': self.source.stat().st_size,
            'clone_path': str(clone), 'clone_verified': False})
        result = ingest(self.root, self.source, self.config)
        self.assertEqual(result['id'], row['id'])
        self.assertEqual(result['status'], 'ready', result['error'])
        self.assertEqual(file_hash(clone), self.hash)
        self.assertFalse(partial.exists())
        self.assertEqual(len([p for p in (self.root / 'jobs').iterdir() if p.is_dir()]), 1)

    def test_concurrent_same_and_distinct_sources_have_no_lost_rows(self):
        another = self.root / 'inbox' / 'other.mkv'
        shutil.copyfile(self.media / 'green.mkv', another)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(self.invoke, 'ingest', path) for path in (self.source, self.source, another, another)]
            results = [future.result() for future in futures]
        for result in results:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = JobStore(self.root).list()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['status'] == 'ready' and row['attempts'] == 1 for row in rows))
        self.assertEqual(len([p for p in (self.root / 'jobs').iterdir() if p.is_dir()]), 2)
        self.assertEqual(file_hash(self.source), self.hash)

    def test_resume_preserves_provenance_and_editorial_work_without_original(self):
        row = ingest(self.root, self.source, self.config)
        job = Path(row['job_path'])
        before = read_json(job / 'manifest.json')
        timeline = job / 'edit/timeline.json'
        work = read_json(timeline)
        work['metadata'] = {'editorial_note': 'do not replace'}
        write_json(timeline, work)
        expected_timeline = file_hash(timeline)
        self.source.unlink()
        result = resume_job(self.root, job, self.config)
        self.assertEqual(result['status'], 'ready', result['error'])
        after = read_json(job / 'manifest.json')
        for field in ('original_path', 'original_size', 'created_at', 'sha256', 'clone_path'):
            self.assertEqual(before[field], after[field])
        self.assertTrue(after['clone_verified'])
        self.assertEqual(after['verification_history'][-1]['evidence'], 'recorded-full-sha256')
        self.assertFalse(Path(after['clone_path']).stat().st_mode & stat.S_IWUSR)
        self.assertEqual(file_hash(timeline), expected_timeline)

    def test_legacy_resume_unverified_missing_original_and_ambiguous_clone(self):
        job = self.root / 'legacy'
        (job / 'source').mkdir(parents=True)
        shutil.copyfile(self.source, job / 'source/one.mkv')
        manifest = {'created_at': '2001-01-01T00:00:00Z', 'original_path': str(self.root / 'gone.mkv'), 'note': 'preserve me'}
        write_json(job / 'manifest.json', manifest)
        result = resume_job(self.root, job, self.config)
        self.assertEqual(result['status'], 'ready', result['error'])
        after = read_json(job / 'manifest.json')
        self.assertFalse(after['clone_verified'])
        self.assertEqual(after['clone_verification_mode'], 'unverified')
        self.assertEqual(after['created_at'], manifest['created_at'])
        self.assertEqual(after['note'], manifest['note'])
        # A recorded clone remains deterministic even with extra source files.
        shutil.copyfile(self.media / 'green.mkv', job / 'source/two.mkv')
        self.assertEqual(resume_job(self.root, job, self.config)['status'], 'ready')
        after.pop('clone_path')
        write_json(job / 'manifest.json', after)
        failed = resume_job(self.root, job, self.config)
        self.assertEqual(failed['error']['code'], 'ambiguous_clone')
        self.assertFalse((job / 'READY.txt').exists())

    def test_resume_mismatch_never_replaces_history_or_marks_ready(self):
        row = ingest(self.root, self.source, self.config)
        job = Path(row['job_path'])
        manifest_hash = file_hash(job / 'manifest.json')
        clone = Path(read_json(job / 'manifest.json')['clone_path'])
        clone.chmod(clone.stat().st_mode | stat.S_IWUSR)
        with clone.open('ab') as stream:
            stream.write(b'corruption')
        failed = resume_job(self.root, job, self.config)
        self.assertEqual(failed['error']['code'], 'clone_mismatch')
        self.assertFalse((job / 'READY.txt').exists())
        self.assertEqual(file_hash(job / 'manifest.json'), manifest_hash)
        self.assertEqual(file_hash(self.source), self.hash)

    def test_legacy_registry_import_is_idempotent_and_preserves_prepared_job(self):
        legacy_root = self.root / 'legacy-root'
        job = legacy_root / 'jobs/old'
        (job / 'source').mkdir(parents=True)
        (job / 'analysis').mkdir()
        shutil.copyfile(self.source, job / 'source/source.mkv')
        (job / 'READY.txt').write_text('READY')
        write_json(job / 'analysis/probe.json', {'streams': []})
        write_json(job / 'manifest.json', {'job_id': 'old-id', 'created_at': '2000-01-01', 'clone_path': str(job / 'source/source.mkv'), 'sha256': self.hash})
        write_json(legacy_root / 'state/processed.json', [{'original_path': str(self.source), 'job_path': str(job)}])
        old_hash = file_hash(legacy_root / 'state/processed.json')
        one, two = JobStore(legacy_root), JobStore(legacy_root)
        self.assertEqual(len(one.list()), 1)
        self.assertEqual(two.latest_ready()['id'], 'old-id')
        self.assertEqual(file_hash(legacy_root / 'state/processed.json'), old_hash)

    def test_audio_only_and_silent_jobs_are_explicit(self):
        audio = self.root / 'inbox/audio.wav'
        shutil.copyfile(self.media / 'voice.wav', audio)
        result = ingest(self.root, audio, self.config)
        self.assertEqual(result['status'], 'ready', result['error'])
        job = Path(result['job_path'])
        self.assertFalse((job / 'edit/timeline.json').exists())
        self.assertFalse((job / 'analysis/contact-sheet.jpg').exists())
        self.assertTrue((job / 'analysis/voiceover.wav').is_file())

    def test_cli_control_flow_and_watcher_health(self):
        first = self.invoke('ingest', self.source)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        row = json.loads(first.stdout)['result']
        self.assertEqual(json.loads(self.invoke('latest-ready').stdout)['result']['id'], row['id'])
        cancelled = self.invoke('cancel', row['id'])
        self.assertEqual(cancelled.returncode, 1)  # cancelled is a structured non-success terminal status
        self.assertEqual(json.loads(cancelled.stdout)['result']['status'], 'cancelled')
        retried = self.invoke('retry', row['id'])
        self.assertEqual(retried.returncode, 0, retried.stdout + retried.stderr)
        health = watch(self.root, self.config_path, once=True)
        stored = read_json(self.root / 'state/watcher-health.json')
        self.assertEqual(stored['status'], 'stopped')
        self.assertIsNotNone(stored['last_success'])
        self.assertTrue((self.root / 'logs/watcher.log').exists())
        report = doctor(self.root, self.config_path)
        self.assertTrue(report['ready'], report)
        self.assertFalse(next(c for c in report['checks'] if c['name'] == 'gemini_credential')['detail']['provider_test_performed'])


if __name__ == '__main__':
    unittest.main()
