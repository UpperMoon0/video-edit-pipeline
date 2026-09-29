"""Real-media regressions for review 5351275447; no encoder/registry mocks."""
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from pipeline.common import PipelineError, file_hash, read_json, write_json
from pipeline.media import run, ffmpeg_args, probe
from pipeline.timeline import normalize
from pipeline.renderer import render
from pipeline.editing import apply_operation
from pipeline.preview import preview_timeline
from pipeline.jobs import ingest
from pipeline.state import JobStore
from test_media import pixel, raw_audio, magnitude


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='review-regression-')
        self.root = Path(self.temp.name)
        for color, frequency in [('red', 440), ('green', 880)]:
            run(ffmpeg_args() + ['-f', 'lavfi', '-i', f'color={color}:s=160x96:r=30:d=2',
                '-f', 'lavfi', '-i', f'sine=frequency={frequency}:sample_rate=48000:duration=2',
                '-c:v', 'ffv1', '-c:a', 'pcm_s16le', str(self.root / (color + '.mkv'))])

    def tearDown(self):
        for path in self.root.rglob('*'):
            if path.is_file():
                path.chmod(path.stat().st_mode | stat.S_IWUSR)
        self.temp.cleanup()

    def timeline(self, source, output='final.mp4', start=0):
        return normalize({'video': {'width': 160, 'height': 96, 'fps': 30},
            'clips': [{'id': 'clip', 'source': str(source), 'in': start, 'duration': 1,
                       'audio': {'mode': 'preserve'}}],
            'encode': {'preset': 'ultrafast'}, 'output': output}, self.root, media=True)

    def assert_red_audio(self, output):
        rgb = pixel(output, .3)
        self.assertGreater(rgb[0], rgb[1] * 3)
        audio = raw_audio(output, .2)
        self.assertGreater(magnitude(audio, 440), magnitude(audio, 880) * 10)

    def test_cache_change_fail_restore_rerender_preserves_picture_and_audio(self):
        source = self.root / 'working.mkv'
        shutil.copyfile(self.root / 'red.mkv', source)
        timeline = self.timeline(source)
        baseline = render(timeline, cache_enabled=False)
        old_hash = file_hash(Path(baseline['output']))
        source_hash = file_hash(source)
        changed = False

        def mutate_before_encode(command, **kwargs):
            nonlocal changed
            if 'ffv1' in command and not changed:
                changed = True
                shutil.copyfile(self.root / 'green.mkv', source)
            return run(command, **kwargs)

        with patch('pipeline.render_chunks.run', side_effect=mutate_before_encode):
            with self.assertRaises(PipelineError):
                render(timeline)
        self.assertTrue(changed)
        self.assertEqual(file_hash(timeline.output), old_hash)
        self.assertEqual(list((self.root / '.pipeline-cache').glob('*.mkv')), [])
        shutil.copyfile(self.root / 'red.mkv', source)
        self.assertEqual(file_hash(source), source_hash)
        recovered = render(self.timeline(source))
        self.assertEqual(recovered['cache_hits'], 0)
        self.assert_red_audio(recovered['output'])
        cached = render(self.timeline(source))
        self.assertEqual(cached['cache_hits'], 1)
        self.assert_red_audio(cached['output'])

    def test_cache_snapshot_survives_source_change_and_restore_during_encode(self):
        source = self.root / 'working.mkv'
        shutil.copyfile(self.root / 'red.mkv', source)
        def mutate_and_restore(command, **kwargs):
            if 'ffv1' not in command:
                return run(command, **kwargs)
            shutil.copyfile(self.root / 'green.mkv', source)
            try:
                return run(command, **kwargs)
            finally:
                shutil.copyfile(self.root / 'red.mkv', source)
        with patch('pipeline.render_chunks.run', side_effect=mutate_and_restore):
            result = render(self.timeline(source))
        self.assert_red_audio(result['output'])
        cached = render(self.timeline(source))
        self.assertEqual(cached['cache_hits'], 1)
        self.assert_red_audio(cached['output'])

    def test_migration_reused_path_and_duplicate_history_preserve_every_job(self):
        for reused in (True, False):
            with self.subTest(reused=reused):
                workspace = self.root / str(reused)
                source = workspace / 'inbox/recording.mkv'
                source.parent.mkdir(parents=True)
                shutil.copyfile(self.root / ('green.mkv' if reused else 'red.mkv'), source)
                entries = []
                for number in range(2):
                    job = workspace / f'jobs/history-{number}'
                    clone = job / 'source/recording.mkv'
                    clone.parent.mkdir(parents=True)
                    shutil.copyfile(self.root / 'red.mkv', clone)
                    write_json(job / 'manifest.json', {'created_at': '2000-01-01',
                        'original_path': str(source), 'clone_path': str(clone), 'sha256': file_hash(clone)})
                    write_json(job / 'analysis/probe.json', probe(clone))
                    (job / 'READY.txt').write_text('READY')
                    entries.append({'original_path': str(source), 'job_path': str(job)})
                registry = workspace / 'state/processed.json'
                write_json(registry, entries)
                historical_hash = file_hash(registry)
                self.assertEqual(len(JobStore(workspace).list()), 2)
                result = ingest(workspace, source, {'stable_seconds': 0, 'contact_sheet_frames': 1})
                self.assertEqual(result['status'], 'ready', result['error'])
                self.assertEqual(len(JobStore(workspace).list()), 3 if reused else 2)
                clone = Path(read_json(Path(result['job_path']) / 'manifest.json')['clone_path'])
                self.assertEqual(file_hash(clone), file_hash(source))
                self.assertEqual(file_hash(registry), historical_hash)
                for entry in entries:
                    old = Path(entry['job_path']) / 'source/recording.mkv'
                    self.assertEqual(file_hash(old), file_hash(self.root / 'red.mkv'))

    def colors(self, output):
        import subprocess
        from pipeline.media import tool
        result = subprocess.run([tool('ffmpeg'), '-v', 'error', '-i', str(output),
            '-vf', 'scale=1:1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'], capture_output=True, check=True)
        return [max(range(3), key=lambda c: result.stdout[i+c]) for i in range(0, len(result.stdout), 3)]

    def test_mixed_rate_split_and_preview_preserve_every_decoded_frame(self):
        for kind in ('24fps', '2fps', 'vfr'):
            source = self.root / (kind + '.mkv')
            filters = 'drawbox=color=green:t=fill:enable=mod(n\\,2)'
            if kind == 'vfr':
                filters += ',select=not(eq(mod(n\\,5)\\,2))'
            run(ffmpeg_args() + ['-f', 'lavfi', '-i',
                f'color=red:s=160x96:r={2 if kind == "2fps" else 24}:d=2',
                '-vf', filters, '-fps_mode', 'vfr', '-c:v', 'ffv1', str(source)])
            for start in (0, .07, .35):
                with self.subTest(kind=kind, start=start):
                    whole = self.timeline(source, f'{kind}-{start}-whole.mp4', start)
                    render(whole, cache_enabled=False)
                    expected = self.colors(whole.output)
                    self.assertEqual(len(expected), 30)
                    for split in (.1, .5):
                        edited = apply_operation(whole, {'op': 'split', 'clip_id': 'clip', 'at': split})
                        edited.spec['output'] = f'{kind}-{start}-{split}-split.mp4'
                        render(edited, cache_enabled=False)
                        self.assertEqual(self.colors(edited.output), expected)
                    preview = preview_timeline(whole, .1, .3, self.root / f'{kind}-{start}-preview.mp4')
                    render(preview, cache_enabled=False)
                    self.assertEqual(self.colors(preview.output), expected[3:9])


if __name__ == '__main__':
    unittest.main()
