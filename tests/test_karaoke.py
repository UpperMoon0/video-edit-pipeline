"""Karaoke regression contracts and real decoded synthetic media; no model download."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'examples')]
from generate_karaoke import generate
from pipeline.common import PipelineError, file_hash, read_json, write_json
from pipeline.karaoke import (SCHEMA, ass_text, build, description, initialize, load_project,
                              lyrics_identity, panel_ranges, remux, render, source_info, subtitle_documents, video_packet_hash)
from pipeline.karaoke_alignment import alignment_groups
from pipeline.media import ffmpeg_args, run, tool


class Karaoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='karaoke-tests-')
        cls.root = generate(Path(cls.temp.name) / 'fixtures')
        cls.base = read_json(cls.root / 'karaoke.json')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def project(self, spec=None):
        path = self.root / ('project-' + self.id().split('.')[-1] + '.json')
        write_json(path, spec or self.base)
        return path

    def frame(self, path, second):
        command = [tool('ffmpeg'), '-v', 'error', '-ss', str(second), '-i', str(path), '-frames:v', '1',
                   '-vf', 'crop=80:50:40:290,scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
        return tuple(subprocess.run(command, check=True, capture_output=True).stdout[:3])

    def gold_pixels(self, path, second):
        command = [tool('ffmpeg'), '-v', 'error', '-ss', str(second), '-i', str(path), '-frames:v', '1',
                   '-vf', 'crop=600:40:20:305', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
        data = subprocess.run(command, check=True, capture_output=True).stdout
        return sum(r > 120 and r > g > b * 1.25 for r, g, b in zip(data[::3], data[1::3], data[2::3]))

    def test_schema_matches_export(self):
        self.assertEqual(SCHEMA, read_json(ROOT / 'schemas/karaoke-v1.schema.json'))

    def test_quantized_mp4_average_rate_uses_the_nominal_frame_grid(self):
        info = {'streams': [{'codec_type': 'video', 'width': 1920, 'height': 1080,
            'avg_frame_rate': '5626000/187533', 'r_frame_rate': '30/1', 'duration': '187.533'},
            {'codec_type': 'audio'}]}
        with patch('pipeline.karaoke.probe', return_value=info):
            self.assertEqual(source_info('quantized.mp4')[3], 30)
            info['streams'][0]['avg_frame_rate'] = '25/1'
            with self.assertRaises(PipelineError):
                source_info('variable.mp4')

    def test_init_does_not_overwrite_an_existing_project(self):
        path = self.root / 'init.json'
        initialize(self.root / 'synthetic.mp4', path, 'New project')
        before = file_hash(path)
        with self.assertRaises(PipelineError):
            initialize(self.root / 'synthetic.mp4', path, 'Replacement')
        self.assertEqual(before, file_hash(path))

    def test_rejects_invalid_timing_and_unknown_fields(self):
        mutations = [lambda s: s.update(unknown=True),
            lambda s: s['cues'][0].update(end=.4),
            lambda s: s['cues'][0].update(start=float('nan')),
            lambda s: s['cues'][1].update(start=1.0),
            lambda s: s['cues'][0]['syllables'][0].update(end=2),
            lambda s: s['cues'][0]['syllables'][1].update(start=.6),
            lambda s: s['cues'][0]['syllables'][0].update(end=.5001)]
        for change in mutations:
            spec = copy.deepcopy(self.base)
            change(spec)
            with self.subTest(change=change), self.assertRaises((PipelineError, ValueError)):
                path = self.project(spec)
                load_project(path, timed=True)

    def test_stale_alignment_rejected_but_translation_is_reusable(self):
        spec = copy.deepcopy(self.base)
        spec['timing_lyrics_sha256'] = lyrics_identity(spec)
        spec['cues'][0]['translation'] = 'A new translation'
        load_project(self.project(spec), timed=True)
        spec['cues'][0]['text'] = 'Changed source lyrics'
        path = self.project(spec)
        with self.assertRaises(PipelineError):
            load_project(path, timed=True)
        _, cleaned, _ = load_project(path, discard_timing=True)
        self.assertNotIn('syllables', cleaned['cues'][0])
        self.assertNotIn('timing_lyrics_sha256', cleaned)

    def test_plain_text_and_credits_do_not_become_ass_commands(self):
        spec = copy.deepcopy(self.base)
        spec['cues'][0]['translation'] = r'{\pos(0,0)} injected'
        ass, srt, _ = subtitle_documents(spec)
        self.assertNotIn(r'{\pos(0,0)} injected', ass)
        self.assertIn('｛＼pos(0,0)｝ injected', ass)
        self.assertIn('00:00:00,500 --> 00:00:01,500', srt)
        spec['style'] = {'font': 'Arial,malformed'}
        with self.assertRaises(PipelineError):
            subtitle_documents(spec)

    def test_description_defaults_and_original_credit_order(self):
        spec = copy.deepcopy(self.base)
        spec['credits'] = [
            {'role': 'reupload', 'name': 'Reuploader', 'url': 'https://example.com/reupload'},
            {'role': 'animation_creator', 'name': 'Original artist', 'url': 'https://example.com/artist'},
            {'role': 'music', 'name': 'Composer', 'url': 'https://example.com/music'}]
        text = description(spec, True)
        self.assertIn('Vocals reduced for karaoke.', text)
        self.assertNotIn('AI', text)
        self.assertLess(text.index('Original artist'), text.index('Reuploader'))
        self.assertIn('not the original creator', text)
        spec['credits'][0]['url'] = 'https://user:secret@example.com/'
        with self.assertRaises(PipelineError):
            load_project(self.project(spec))

    def test_panel_and_alignment_groups_leave_instrumental_breaks(self):
        self.assertEqual(len(panel_ranges([{'start': 1, 'end': 2}, {'start': 2.5, 'end': 3}, {'start': 10, 'end': 11}])), 2)
        self.assertEqual(len(alignment_groups([{'start': 0, 'end': 20}, {'start': 20, 'end': 29}])), 2)

    def test_build_is_local_and_changed_translation_creates_new_bundle(self):
        path = self.project()
        before = file_hash(self.root / 'synthetic.mp4')
        with patch.dict(sys.modules, {'faster_whisper': None, 'onnxruntime': None}):
            first = build(path)
        self.assertEqual(first['identity'], build(path)['identity'])
        spec = read_json(path)
        spec['cues'][0]['translation'] = 'Different words'
        write_json(path, spec)
        self.assertNotEqual(first['identity'], build(path)['identity'])
        self.assertEqual(before, file_hash(self.root / 'synthetic.mp4'))
        self.assertTrue(Path(first['ass']).is_file())

    def test_real_render_preview_panel_and_audio_only_export(self):
        path = self.project()
        master = self.root / 'master.mp4'
        report = render(path, master)
        self.assertTrue(report['qa']['passed'])
        # Uniform synthetic picture makes panel presence measurable, independently of text.
        self.assertLess(sum(self.frame(master, 1)), sum(self.frame(master, 2.4)) * .5)
        self.assertGreater(self.gold_pixels(master, 1.4), self.gold_pixels(master, .6) + 10)
        preview = self.root / 'preview.mp4'
        preview_result = render(path, preview, start=.8, duration=.5)
        self.assertEqual(preview_result['qa']['metrics']['video_frames'], 15)
        self.assertLess(sum(self.frame(preview, .1)), sum(self.frame(master, 2.4)) * .5)
        changed = self.root / 'instrumental.mp4'
        old_hash = file_hash(master)
        mixed = remux(master, self.root / 'replacement.wav', changed)
        self.assertTrue(mixed['qa']['picture_packets_unchanged'])
        self.assertEqual(video_packet_hash(master), video_packet_hash(changed))
        def audio_hash(p):
            return run(ffmpeg_args() + ['-i', str(p), '-vn', '-f', 'hash', '-']).stdout
        self.assertNotEqual(audio_hash(master), audio_hash(changed))
        self.assertEqual(old_hash, file_hash(master))

    def test_failed_render_preserves_previous_output_and_source_alias(self):
        path = self.project()
        output = self.root / 'preserved.mp4'
        output.write_bytes(b'previous approved master')
        before = file_hash(output)
        with patch('pipeline.karaoke.inspect_output', side_effect=PipelineError('test_failure', 'qa', 'Injected QA failure')):
            with self.assertRaises(PipelineError):
                render(path, output)
        self.assertEqual(before, file_hash(output))
        source = self.root / 'synthetic.mp4'
        source_hash = file_hash(source)
        with self.assertRaises(PipelineError):
            render(path, source)
        self.assertEqual(source_hash, file_hash(source))

    def test_cli_json_and_short_replacement_rejection(self):
        path = self.project()
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/karaoke.py'), 'build', str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
        short = self.root / 'too-short.wav'
        run(ffmpeg_args() + ['-f', 'lavfi', '-i', 'sine=duration=1', str(short)])
        with self.assertRaises(PipelineError):
            remux(self.root / 'synthetic.mp4', short, self.root / 'must-not-exist.mp4')
        self.assertFalse((self.root / 'must-not-exist.mp4').exists())


if __name__ == '__main__':
    unittest.main()
