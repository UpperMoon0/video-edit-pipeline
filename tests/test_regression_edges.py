"""Edge evidence for timestamps, stale readiness, optional ASR, and repository privacy."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'examples')]
from generate_fixtures import generate
from pipeline.common import PipelineError, file_hash, read_json, write_json
from pipeline.captions import selected_cues, retime
from pipeline.media import ffmpeg_args, run, probe
from pipeline.timeline import normalize
from pipeline.renderer import render, command_plan
from pipeline.jobs import ingest
from pipeline.state import JobStore
from transcribe import transcribe_job


class EdgeContracts(unittest.TestCase):
    def test_optional_transcription_is_local_by_default_and_transactional(self):
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory)
            (job / 'analysis').mkdir()
            audio = job / 'analysis/voiceover.wav'
            audio.write_bytes(b'fake-audio-for-mocked-ASR-only')
            original = file_hash(audio)
            calls = []
            segment = NS(start=0, end=1, text=' Chào Sunday ', words=[NS(start=.1, end=.9, word='Chào Sunday', probability=.99)])
            info = NS(language='vi', language_probability=.99, duration=1)
            def factory(model, **kwargs):
                calls.append(kwargs)
                return NS(transcribe=lambda *args, **options: (iter([segment]), info))
            result = transcribe_job(job, model='mock', model_factory=factory)
            self.assertTrue(calls[0]['local_files_only'])
            self.assertEqual(result['segments'][0]['text'], 'Chào Sunday')
            self.assertTrue(Path(result['srt']).is_file())
            self.assertTrue(Path(result['text_file']).is_file())
            previous = file_hash(job / 'analysis/transcript.json')
            def incomplete():
                yield segment
                raise RuntimeError('injected ASR interruption')
            failing = lambda *args, **kwargs: NS(transcribe=lambda *a, **k: (incomplete(), info))
            with self.assertRaises(RuntimeError):
                transcribe_job(job, model_factory=failing)
            self.assertEqual(file_hash(job / 'analysis/transcript.json'), previous)
            self.assertEqual(file_hash(audio), original)

    def test_caption_validation_status_markup_and_muted_narration(self):
        source = {'status': 'complete', 'segments': [{'start': 0, 'end': 1, 'text': '<b>hello</b>\n\n{\\pos(0,0)} world'}]}
        self.assertEqual(selected_cues(source, 0, 1, 0)[0]['text'], 'hello world')
        source['status'] = 'awaiting_transcription'
        self.assertEqual(selected_cues(source, 0, 1, 0), [])
        for segment in ({'start': float('inf'), 'end': 2, 'text': 'bad'}, {'start': 2, 'end': 1, 'text': 'bad'},
                        {'start': 0, 'end': 1, 'text': 1}, {'start': 0, 'end': 1, 'text': 'bad', 'words': [{}]}):
            with self.subTest(segment=segment), self.assertRaises(PipelineError):
                selected_cues({'segments': [segment]}, 0, 3, 0)
        timeline = NS(spec={'audio': {'voiceover_volume': 0}, 'captions': {'kind': 'narration'}})
        self.assertEqual(retime(timeline), [])

    def test_doctor_fails_closed_for_missing_unsupported_and_unwritable_environments(self):
        from pipeline.operations import doctor
        from pipeline.media import run as real_run
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.json'
            write_json(config, {'inbox_paths': ['inbox'], 'extensions': ['.mkv']})
            with patch('pipeline.operations.tool', side_effect=PipelineError('missing_tool', 'ffmpeg', 'not installed')):
                report = doctor(root, config)
                self.assertFalse(report['ready'])
                self.assertFalse(next(c for c in report['checks'] if c['name'] == 'ffmpeg')['ok'])
            def unsupported(command, **kwargs):
                if '-version' in command:
                    return subprocess.CompletedProcess(command, 0, 'ffmpeg version 4.4 unsupported\n', '')
                return real_run(command, **kwargs)
            with patch('pipeline.operations.run', side_effect=unsupported):
                self.assertFalse(doctor(root, config)['ready'])
            real_temporary_file = tempfile.TemporaryFile
            def readonly_workspace(*args, **kwargs):
                if kwargs.get('dir') is not None and Path(kwargs['dir']).resolve() == root.resolve():
                    raise PermissionError('readonly workspace')
                return real_temporary_file(*args, **kwargs)
            with patch('pipeline.operations.tempfile.TemporaryFile', side_effect=readonly_workspace):
                report = doctor(root, config)
                self.assertFalse(report['ready'])
                self.assertFalse(next(c for c in report['checks'] if c['name'] == 'storage')['ok'])
            with patch('pipeline.operations.shutil.disk_usage', return_value=NS(total=1000, used=999, free=1)):
                self.assertFalse(doctor(root, config)['ready'])
            config.write_text('not valid JSON', encoding='utf-8')
            self.assertFalse(doctor(root, config)['ready'])

    def test_repository_deny_by_default_preserves_source_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            subprocess.run(['git', 'init', '-q', str(directory)], check=True)
            shutil.copyfile(ROOT / '.gitignore', directory / '.gitignore')
            ignored = ['jobs/secret/manifest.json', 'state/jobs.sqlite3', 'logs/watch.log', '.env', 'config.json',
                       'personal-plan.md', 'footage.mp4', 'tools/pwsh.exe', 'examples/private.wav', 'docs/private.png']
            allowed = ['README.md', 'CONTRIBUTING.md', 'requirements.txt', 'scripts/pipeline/renderer.py',
                       'tests/test_media.py', 'schemas/timeline-v1.schema.json', 'examples/generate_fixtures.py',
                       'docs/TIMELINE.md', '.github/workflows/ci.yml']
            for path in ignored + allowed:
                result = subprocess.run(['git', 'check-ignore', '-q', path], cwd=directory)
                self.assertEqual(result.returncode == 0, path in ignored, path)


class MediaEdges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='pipeline-edges-')
        cls.root = generate(Path(cls.temp.name))

    @classmethod
    def tearDownClass(cls):
        for path in cls.root.rglob('*'):
            if path.is_file():
                path.chmod(path.stat().st_mode | stat.S_IWUSR)
        cls.temp.cleanup()

    def make_timeline(self, source, duration, name):
        return normalize({'video': {'width': 160, 'height': 96, 'fps': 30},
            'clips': [{'source': source, 'duration': duration, 'audio': {'mode': 'preserve'}}],
            'encode': {'preset': 'ultrafast'}, 'output': 'output/' + name + '.mp4'}, self.root, media=True)

    def test_video_bounds_ignore_longer_audio_container_duration(self):
        asset = self.root / 'long-audio.mkv'
        run(ffmpeg_args() + ['-f', 'lavfi', '-i', 'color=red:s=160x96:r=30:d=1',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=3',
            '-c:v', 'libx264', '-threads', '1', '-c:a', 'pcm_s16le', str(asset)])
        self.assertGreater(float(probe(asset)['format']['duration']), 2.9)
        with self.assertRaises(PipelineError) as error:
            self.make_timeline(str(asset), 2, 'long-audio-fail')
        self.assertEqual(error.exception.code, 'source_range')
        output = render(self.make_timeline(str(asset), 1, 'long-audio-good'), cache_enabled=False)
        self.assertEqual(output['frames'], 30)

    def test_nonzero_source_start_and_vfr_frame_normalization(self):
        shifted = self.root / 'shifted.mkv'
        run(ffmpeg_args() + ['-i', str(self.root / 'red.mkv'), '-vf', 'setpts=PTS+5/TB', '-af', 'asetpts=PTS+5/TB',
            '-c:v', 'libx264', '-threads', '1', '-c:a', 'pcm_s16le', str(shifted)])
        self.assertGreater(float(probe(shifted)['format']['start_time']), 4.9)
        result = render(self.make_timeline(str(shifted), 1, 'shifted'), cache_enabled=False)
        self.assertEqual(result['frames'], 30)
        vfr = self.root / 'vfr.mkv'
        run(ffmpeg_args() + ['-i', str(self.root / 'red.mkv'), '-an',
            '-vf', 'select=if(lt(t\\,1)\\,not(mod(n\\,3))\\,1)', '-fps_mode', 'vfr',
            '-c:v', 'libx264', '-threads', '1', str(vfr)])
        self.assertLess(int(probe(vfr, True)['streams'][0]['nb_read_frames']), 90)
        result = render(self.make_timeline(str(vfr), 2, 'vfr'), cache_enabled=False)
        self.assertEqual(result['frames'], 60)

    def test_latest_ready_excludes_a_missing_verified_clone_without_recloning(self):
        config = {'stable_seconds': 0, 'contact_sheet_frames': 1}
        workspace = self.root / 'jobs-workspace'
        row = ingest(workspace, self.root / 'green.mkv', config)
        self.assertEqual(row['status'], 'ready', row['error'])
        clone = Path(read_json(Path(row['job_path']) / 'manifest.json')['clone_path'])
        clone.chmod(clone.stat().st_mode | stat.S_IWUSR)
        clone.unlink()
        with self.assertRaises(PipelineError):
            JobStore(workspace).latest_ready()
        again = ingest(workspace, self.root / 'green.mkv', config)
        self.assertEqual(again['status'], 'stale')
        self.assertEqual(again['id'], row['id'])
        self.assertEqual(len(JobStore(workspace).list()), 1)

    def test_loudness_dry_run_includes_measurement_stage_without_writes(self):
        timeline = self.make_timeline('red.mkv', 2, 'loudness-plan')
        timeline.spec['audio'] = {'loudness': {'integrated': -16, 'true_peak': -1}}
        before = set(self.root.rglob('*'))
        plan = command_plan(timeline)
        self.assertEqual(len(plan['commands']), 3)
        self.assertIn('print_format=json', plan['filter_graphs'][1])
        self.assertIn('{measured-at-runtime}', plan['filter_graphs'][2])
        self.assertEqual(set(self.root.rglob('*')), before)


if __name__ == '__main__':
    unittest.main()
