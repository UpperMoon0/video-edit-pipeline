"""Real FFmpeg integration regressions, including decoded pixels and audio."""
import array
import copy
import json
import math
import os
import shutil
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
from pipeline.media import ffmpeg_args, run, probe, tool
from pipeline.timeline import load_timeline, normalize, rate
from pipeline.renderer import render, command_plan
from pipeline.sampling import sample_video
from pipeline.editing import edit_timeline, convert_scaffold
from pipeline.preview import preview_timeline
from pipeline.footage import build_index, query_index


def raw_audio(path, start=0, duration=.5):
    result = subprocess.run([tool('ffmpeg'), '-v', 'error', '-ss', f'{start:.9f}', '-i', str(path), '-t', f'{duration:.9f}',
        '-vn', '-f', 'f32le', '-ac', '1', '-ar', '48000', '-'], check=True, capture_output=True)
    return array.array('f', result.stdout)


def rms(samples):
    return math.sqrt(sum(float(v) ** 2 for v in samples) / max(1, len(samples)))


def magnitude(samples, frequency):
    return abs(sum(v * complex(math.cos(2 * math.pi * frequency * i / 48000), math.sin(2 * math.pi * frequency * i / 48000))
                   for i, v in enumerate(samples))) / len(samples)


def pixel(path, timestamp):
    result = subprocess.run([tool('ffmpeg'), '-v', 'error', '-ss', f'{timestamp:.9f}', '-i', str(path),
        '-frames:v', '1', '-vf', 'scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], check=True, capture_output=True)
    return tuple(result.stdout[:3])


class MediaIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which(os.environ.get('PIPELINE_FFMPEG', 'ffmpeg')):
            raise RuntimeError('Real FFmpeg is required; these tests must not silently skip media coverage.')
        cls.temp = tempfile.TemporaryDirectory(prefix='video-media-')
        cls.root = generate(Path(cls.temp.name))
        cls.config = read_json(cls.root / 'minimal.json')
        run(ffmpeg_args() + ['-f', 'lavfi', '-i', 'color=black:s=160x96:r=30:d=1', '-an', '-c:v', 'libx264', '-threads', '1', str(cls.root / 'silent.mp4')])
        run(ffmpeg_args() + ['-f', 'lavfi', '-i', 'color=blue:s=160x96:r=30:d=0.033334', '-frames:v', '1', '-c:v', 'libx264', '-threads', '1', str(cls.root / 'one-frame.mkv')])
        run(ffmpeg_args() + ['-f', 'lavfi', '-i', 'color=black:s=160x96:r=30:d=1[b];color=white:s=160x96:r=30:d=1[w];[b][w]concat=n=2:v=1:a=0',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=2', '-c:v', 'libx264', '-threads', '1', '-c:a', 'pcm_s16le', str(cls.root / 'scene.mkv')])
        run(ffmpeg_args() + ['-i', str(cls.root / 'red.mkv'), '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=48000:duration=3',
            '-map', '0:v:0', '-map', '0:a:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'pcm_s16le', str(cls.root / 'multi.mkv')])
        cls.annotated = {'version': 1, 'status': 'complete', 'segments': [
            {'start': 0, 'end': 1, 'text': 'alpha', 'words': [{'start': .1, 'end': .7, 'text': 'alpha'}]},
            {'start': 1, 'end': 2, 'text': 'beta', 'words': [{'start': 1.1, 'end': 1.7, 'text': ' beta'}]}]}
        write_json(cls.root / 'transcript.json', cls.annotated)

    @classmethod
    def tearDownClass(cls):
        # All inputs here are generated fixtures; no caller media is touched.
        cls.temp.cleanup()

    def spec(self, name):
        spec = copy.deepcopy(self.config)
        spec['output'] = 'output/' + name + '.mp4'
        return spec

    def render_spec(self, spec, cache=False):
        timeline = normalize(spec, self.root, media=True)
        return render(timeline, cache_enabled=cache), timeline

    def test_short_narration_keeps_late_music_and_sfx(self):
        spec = self.spec('short-voice')
        spec['audio']['sfx'] = [{'source': 'effect.wav', 'start': 3, 'duration': .3, 'volume': .5}]
        result, _ = self.render_spec(spec)
        self.assertEqual(result['frames'], 120)
        samples = raw_audio(result['output'], 2.5)
        self.assertGreater(rms(samples), .02)
        sfx = raw_audio(result['output'], 3.02, .2)
        self.assertGreater(magnitude(sfx, 1500), .01)
        self.assertLess(abs(float(next(s for s in probe(Path(result['output']))['streams'] if s['codec_type'] == 'audio')['duration']) - 4), .06)

    def test_audio_short_long_source_only_music_only_and_silent(self):
        for case in ('short-only', 'long-only', 'source-only', 'music-only', 'silent'):
            with self.subTest(case=case):
                spec = self.spec(case)
                if case == 'short-only':
                    spec['audio'] = {'voiceover': 'voice.wav'}
                elif case == 'long-only':
                    spec['clips'] = spec['clips'][:1]
                    spec['audio'] = {'voiceover': 'music.wav'}
                elif case == 'source-only':
                    spec.pop('audio')
                    for clip in spec['clips']:
                        clip['audio'] = {'mode': 'preserve'}
                elif case == 'music-only':
                    spec['audio'].pop('voiceover')
                else:
                    spec.pop('audio')
                result, _ = self.render_spec(spec)
                late = rms(raw_audio(result['output'], result['duration'] - .6, .4))
                self.assertLess(late, .00001) if case in ('short-only', 'silent') else self.assertGreater(late, .015)

    def test_select_original_audio_stream_and_silent_source(self):
        spec = self.spec('selected-track')
        spec['clips'] = [{'source': 'multi.mkv', 'duration': 1, 'audio': {'mode': 'preserve', 'stream': 1, 'gain': .5}}]
        spec.pop('audio')
        result, _ = self.render_spec(spec)
        audio = raw_audio(result['output'], .2)
        self.assertGreater(magnitude(audio, 880), 10 * magnitude(audio, 440))
        spec['clips'] = [{'source': 'silent.mp4', 'duration': 1, 'audio': {'mode': 'preserve'}}]
        result, _ = self.render_spec(spec)
        self.assertLess(rms(raw_audio(result['output'], .2)), .000001)
        spec['clips'][0]['audio']['stream'] = 1
        with self.assertRaises(PipelineError):
            normalize(spec, self.root, media=True)

    def test_fractional_real_frame_rates(self):
        for fps in ('30000/1001', '24000/1001', 29.97, 23.976):
            with self.subTest(fps=fps):
                spec = self.spec('fractional-' + str(fps).replace('/', '-'))
                spec['video']['fps'] = fps
                spec['clips'] = [{'source': 'red.mkv', 'duration': 1}]
                spec.pop('audio')
                result, _ = self.render_spec(spec)
                stream = next(s for s in probe(Path(result['output']), True)['streams'] if s['codec_type'] == 'video')
                self.assertEqual(rate(stream['avg_frame_rate']), rate(fps))
                self.assertEqual(int(stream['nb_read_frames']), result['frames'])

    def test_source_bounds_fail_before_output_mutation(self):
        spec = self.spec('bounds')
        output = self.root / spec['output']
        output.parent.mkdir(exist_ok=True)
        output.write_bytes(b'last-good')
        for start, duration in [(3, 1), (2.5, 1), (4, .1), (-1, .1)]:
            spec['clips'] = [{'source': 'red.mkv', 'in': start, 'duration': duration}]
            spec.pop('audio', None)
            with self.subTest(start=start), self.assertRaises(PipelineError):
                self.render_spec(spec)
            self.assertEqual(output.read_bytes(), b'last-good')

    def test_failed_encode_qa_and_cancellation_preserve_output(self):
        spec = self.spec('preserved')
        result, timeline = self.render_spec(spec, cache=True)
        expected = file_hash(Path(result['output']))
        original_run = run
        def fail_final(command, **kwargs):
            if '-c:v' in command and command[command.index('-c:v') + 1] == 'libx264':
                Path(command[-1]).write_bytes(b'partial')
                raise PipelineError('injected_encode', 'test', 'encode failure')
            return original_run(command, **kwargs)
        with patch('pipeline.renderer.run', side_effect=fail_final), self.assertRaises(PipelineError):
            render(timeline)
        self.assertEqual(file_hash(timeline.output), expected)
        bad = normalize({**spec, 'qa': {'max_black_seconds': 0}, 'clips': [{'source': 'silent.mp4', 'duration': 1}], 'audio': {}}, self.root, media=True)
        with self.assertRaises(PipelineError):
            render(bad)
        self.assertEqual(file_hash(timeline.output), expected)
        with self.assertRaises(PipelineError):
            render(timeline, cancel=lambda: True)
        self.assertEqual(file_hash(timeline.output), expected)
        self.assertEqual(list(timeline.output.parent.glob('.render-work-*')), [])
        self.assertEqual(list(timeline.output.parent.glob('.*.render-*.mp4')), [])

    def test_cache_equivalence_and_input_change_invalidation(self):
        spec = self.spec('cache')
        for clip in spec['clips']:
            clip['audio'] = {'mode': 'preserve', 'gain': .7}
        first, timeline = self.render_spec(spec, cache=True)
        cached = render(timeline)
        uncached = render(timeline, cache_enabled=False)
        self.assertEqual(cached['cache_hits'], 2)
        self.assertEqual(first['sha256'], cached['sha256'])
        self.assertEqual(first['sha256'], uncached['sha256'])
        spec['clips'][0]['audio']['gain'] = .8
        changed, _ = self.render_spec(spec, cache=True)
        self.assertEqual(changed['cache_hits'], 1)
        self.assertNotEqual(changed['sha256'], first['sha256'])
        for t in (1.95, 2.01):
            rgb = pixel(timeline.output, t)
            self.assertGreater(rgb[0], rgb[1]) if t < 2 else self.assertGreater(rgb[1], rgb[0])

    def test_240_cuts_long_unicode_asset_paths_with_bounded_commands(self):
        directory = self.root / ('Unicode Chào 日本語 ' + 'asset' * 20)
        directory.mkdir(exist_ok=True)
        asset = directory / 'đoạn nguồn.mkv'
        shutil.copyfile(self.root / 'red.mkv', asset)
        spec = self.spec('many-cuts')
        spec['clips'] = [{'source': str(asset), 'duration': 1/30} for _ in range(240)]
        spec.pop('audio')
        timeline = normalize(spec, self.root, media=True)
        plan = command_plan(timeline)
        from pipeline.media import windows_command_units
        self.assertTrue(all(windows_command_units(command) <= 32000 for command in plan['commands']))
        self.assertGreater(len(str(asset)) * len(spec['clips']), 32000)
        result = render(timeline)
        self.assertEqual(result['frames'], 240)
        self.assertGreaterEqual(result['cache_hits'], 239)
        self.assertLessEqual(sum(p.stat().st_size for p in (timeline.output.parent / '.pipeline-cache').glob('*.mkv')), 1024**3)

    def test_dry_run_no_writes_and_external_graphs(self):
        spec = self.spec('dry-inspect')
        spec['titles'] = [{'text': 'Chào: 50% {not an expression}', 'start': 0, 'duration': 1, 'size': 16}]
        timeline = normalize(spec, self.root, media=True)
        before = {str(p) for p in self.root.rglob('*')}
        plan = command_plan(timeline)
        self.assertFalse(plan['writes_performed'])
        self.assertTrue(all('-filter_complex_script' in c for c in plan['commands']))
        self.assertEqual(before, {str(p) for p in self.root.rglob('*')})

    def test_sampling_short_eof_precision_stale_frames_and_invalid_inputs(self):
        output = self.root / 'sampling'
        result = sample_video(self.root / 'silent.mp4', output, interval=.1, start=.8, end=1)
        self.assertTrue(all(.8 <= f['timestamp'] < 1 for f in result['frames']))
        previous = output / result['run']
        single = sample_video(self.root / 'one-frame.mkv', output, count=1)
        self.assertEqual(single['frame_count'], 1)
        self.assertLess(single['frames'][0]['timestamp'], .034)
        self.assertFalse(previous.exists())
        index_hash = file_hash(output / 'index.json')
        for kwargs in ({'interval': 0}, {'columns': 0}, {'rows': -1}, {'width': 0}, {'start': -1}, {'start': 2}, {'end': float('nan')}, {'start': .8, 'end': .7}):
            with self.subTest(kwargs=kwargs), self.assertRaises(PipelineError):
                sample_video(self.root / 'silent.mp4', output, **kwargs)
            self.assertEqual(file_hash(output / 'index.json'), index_hash)
        with patch('pipeline.sampling.run', return_value=subprocess.CompletedProcess([], 0, '', '')), self.assertRaises(PipelineError):
            sample_video(self.root / 'silent.mp4', output, count=1)
        self.assertEqual(file_hash(output / 'index.json'), index_hash)

    def test_ducking_and_measured_loudness(self):
        dry = self.spec('dry-mix')
        plain, _ = self.render_spec(dry)
        duck = copy.deepcopy(dry)
        duck['output'] = 'output/duck.mp4'
        duck['audio']['ducking'] = {'enabled': True, 'threshold': .005, 'ratio': 8}
        ducked, _ = self.render_spec(duck)
        self.assertLess(magnitude(raw_audio(ducked['output'], .3), 220), .5 * magnitude(raw_audio(plain['output'], .3), 220))
        self.assertAlmostEqual(magnitude(raw_audio(ducked['output'], 2.5), 220), magnitude(raw_audio(plain['output'], 2.5), 220), delta=.002)
        loud = self.spec('loudnorm')
        loud['audio']['loudness'] = {'integrated': -16, 'true_peak': -1}
        result, _ = self.render_spec(loud)
        report = read_json(Path(result['qa_report']))
        self.assertTrue(report['passed'])
        self.assertLess(abs(report['metrics']['integrated_lufs'] + 16), 2)
        self.assertLessEqual(report['metrics']['true_peak_db'], -.7)

    def test_titles_captions_mux_burn_and_cut_retiming(self):
        for mode in ('sidecar', 'mux', 'burn'):
            with self.subTest(mode=mode):
                spec = self.spec('captions-' + mode)
                spec['clips'] = [
                    {'id': 'later', 'source': 'red.mkv', 'in': 1, 'duration': 1, 'audio': {'mode': 'preserve'}, 'transcript': 'transcript.json'},
                    {'id': 'early', 'source': 'green.mkv', 'duration': 1, 'audio': {'mode': 'preserve'}, 'transcript': 'transcript.json'},
                    {'id': 'muted', 'source': 'red.mkv', 'duration': 1, 'transcript': 'transcript.json'}]
                spec['audio'] = {}
                spec['captions'] = {'kind': 'source', 'mode': mode, 'size': 14}
                spec['titles'] = [{'text': 'Chào: 50% {safe}', 'start': .2, 'duration': .5, 'size': 14, 'x': 'center', 'y': 'top', 'box': True}]
                result, _ = self.render_spec(spec)
                report = read_json(Path(result['qa_report']))
                text = Path(report['captions_sidecar']).read_text()
                self.assertIn('00:00:00,100 --> 00:00:00,700\nbeta', text)
                self.assertIn('00:00:01,100 --> 00:00:01,700\nalpha', text)
                self.assertEqual(text.count('-->'), 2)
                streams = probe(Path(result['output']))['streams']
                self.assertEqual(any(s['codec_type'] == 'subtitle' for s in streams), mode == 'mux')
                self.assertNotEqual(pixel(result['output'], .4), pixel(result['output'], .9))

    def test_revision_edits_preview_and_nonoverwriting_conversion(self):
        spec = self.spec('edited')
        spec['audio'] = {}
        timeline_file = self.root / 'editing.json'
        write_json(timeline_file, spec)
        result = edit_timeline(timeline_file, 0, {'op': 'split', 'clip_id': 'red', 'at': 1})
        self.assertEqual(result['revision'], 1)
        ids = [c['id'] for c in result['timeline']['clips']]
        with self.assertRaises(PipelineError):
            edit_timeline(timeline_file, 0, {'op': 'reorder', 'clip_ids': list(reversed(ids))})
        result = edit_timeline(timeline_file, 1, {'op': 'reorder', 'clip_ids': list(reversed(ids))})
        result = edit_timeline(timeline_file, 2, {'op': 'undo', 'revision': 0})
        self.assertEqual(result['revision'], 3)
        self.assertEqual([c['id'] for c in result['timeline']['clips']], ['red', 'green'])
        original = load_timeline(timeline_file, media=True)
        ranged = preview_timeline(original, 1.5, 2.5, self.root / 'preview.mp4')
        result = render(ranged, cache_enabled=False)
        self.assertEqual(result['frames'], 30)
        self.assertGreater(pixel(result['output'], .2)[0], pixel(result['output'], .2)[1])
        self.assertGreater(pixel(result['output'], .7)[1], pixel(result['output'], .7)[0])
        self.assertFalse(original.output.exists())
        scaffold = self.root / 'scaffold.json'
        write_json(scaffold, {'version': 1, 'source': 'red.mkv', 'cuts': [], 'output': 'output/converted.mp4'})
        converted = self.root / 'converted.json'
        convert_scaffold(scaffold, converted)
        with self.assertRaises(PipelineError):
            convert_scaffold(scaffold, converted)
        self.assertIn('clips', read_json(converted))
        self.assertIn('cuts', read_json(scaffold))

    def test_footage_index_shots_text_time_pagination_and_invalidation(self):
        index = self.root / 'footage.sqlite3'
        result = build_index(self.root / 'scene.mkv', index, transcript=self.root / 'transcript.json')
        self.assertEqual(result['status'], 'indexed')
        self.assertEqual(result['shots'], 2)
        again = build_index(self.root / 'scene.mkv', index, transcript=self.root / 'transcript.json')
        self.assertEqual(again['status'], 'cached')
        found = query_index(index, text='BETA')
        self.assertEqual(len(found['items']), 1)
        self.assertEqual(found['items'][0]['source_range']['in'], 1)
        self.assertTrue(Path(found['items'][0]['nearby_sample']['frame']).is_file())
        page = query_index(index, kind='shot', limit=1)
        self.assertEqual(page['next_offset'], 1)
        self.assertEqual(query_index(index, kind='shot', limit=1, offset=1)['items'][0]['source_range']['in'], 1)
        changed = self.root / 'index-changing.mkv'
        shutil.copyfile(self.root / 'red.mkv', changed)
        build_index(changed, index)
        shutil.copyfile(self.root / 'green.mkv', changed)
        stale = query_index(index, kind='shot')
        self.assertEqual(len(stale['stale_assets']), 1)
        rebuilt = build_index(changed, index)
        self.assertEqual(rebuilt['status'], 'indexed')
        self.assertEqual(query_index(index, kind='shot')['stale_assets'], [])


if __name__ == '__main__':
    unittest.main()
