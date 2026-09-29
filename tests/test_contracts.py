"""Fast deterministic contracts; no provider calls or model downloads."""
import base64
import copy
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from pipeline.common import PipelineError, FileLock, read_json, write_json, output_transaction, file_hash
from pipeline.timeline import normalize, rate, frame_count
from pipeline.schema import SCHEMA
from pipeline.media import check_command, windows_command_units, run, Cancelled
from pipeline.tts import extract_audio, publish_response
from pipeline.captions import selected_cues
from pipeline.operations import config_read
from pipeline.state import JobStore


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='video-contract-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'source.mp4').write_bytes(b'original-media-placeholder')
        self.spec = {'video': {'width': 160, 'height': 96, 'fps': 30},
            'clips': [{'source': 'source.mp4', 'duration': 2}], 'output': 'output/final.mp4'}

    def test_bom_reader_and_writer_policy(self):
        p = self.root / 'bom.json'
        p.write_text(json.dumps({'title': 'Chào Sunday 日本語'}, ensure_ascii=False), encoding='utf-8-sig')
        self.assertEqual(read_json(p)['title'], 'Chào Sunday 日本語')
        write_json(p, read_json(p))
        self.assertFalse(p.read_bytes().startswith(b'\xef\xbb\xbf'))

    def test_exported_schema_is_runtime_schema(self):
        self.assertEqual(read_json(ROOT / 'schemas/timeline-v1.schema.json'), SCHEMA)

    def test_structural_validation_does_not_launch_media_or_create_output(self):
        with patch('pipeline.media.subprocess.Popen', side_effect=AssertionError('No process allowed')):
            timeline = normalize(self.spec, self.root)
        self.assertEqual(timeline.duration, 2)
        self.assertFalse((self.root / 'output').exists())

    def test_schema_rejects_bad_values(self):
        cases = []
        def changed(field, value):
            spec = copy.deepcopy(self.spec)
            current = spec
            for key in field[:-1]:
                current = current[key]
            current[field[-1]] = value
            cases.append(spec)
        for fps in (0, -1, True, '0/0', 'nan', float('nan'), float('inf')):
            changed(['video', 'fps'], fps)
        for duration in (0, -1, True, float('inf'), 'two'):
            changed(['clips', 0, 'duration'], duration)
        changed(['video', 'width'], 161)
        changed(['video', 'width'], 160.5)
        changed(['clips', 0, 'in'], -1)
        changed(['clips', 0, 'source'], 'missing.mp4')
        changed(['clips', 0, 'type'], 'unknown')
        changed(['clips', 0, 'audio'], {'mode': 'preserve', 'stream': -1})
        changed(['version'], 2)
        changed(['unknown'], 1)
        changed(['clips'], [])
        for spec in cases:
            with self.subTest(spec=spec), self.assertRaises(PipelineError):
                normalize(spec, self.root)

    def test_fractional_rate_and_single_frame_rounding(self):
        for fps in ('30000/1001', '24000/1001', 29.97, 23.976):
            spec = copy.deepcopy(self.spec)
            spec['video']['fps'] = fps
            timeline = normalize(spec, self.root)
            self.assertEqual(timeline.fps, rate(fps))
            self.assertEqual(timeline.duration, float(sum(timeline.frames) / rate(fps)))
        self.assertNotEqual(rate(29.97), rate('30000/1001'))
        self.assertEqual(frame_count(.05, rate(30)), 2)
        self.spec['clips'][0]['duration'] = .0001
        with self.assertRaises(PipelineError):
            normalize(self.spec, self.root)

    def test_alias_rejects_same_path_hardlink_and_symlink(self):
        for name, create in [('source.mp4', None), ('hard.mp4', 'hard'), ('sym.mp4', 'sym')]:
            if create:
                try:
                    if create == 'hard':
                        (self.root / name).hardlink_to(self.root / 'source.mp4')
                    else:
                        (self.root / name).symlink_to(self.root / 'source.mp4')
                except OSError:
                    continue
            spec = copy.deepcopy(self.spec)
            spec['output'] = name
            with self.assertRaises(PipelineError) as error:
                normalize(spec, self.root)
            self.assertEqual(error.exception.code, 'input_output_alias')

    def test_atomic_failure_and_rename_failure_preserve_last_good(self):
        output = self.root / 'good.mp4'
        output.write_bytes(b'last-good')
        for fail_at in ('body', 'replace'):
            with self.subTest(fail_at=fail_at):
                def execute():
                    with output_transaction(output, [self.root / 'source.mp4']) as staged:
                        self.assertEqual(staged.suffix, '.mp4')
                        staged.write_bytes(b'partial-new')
                        if fail_at == 'body':
                            raise RuntimeError('injected failure')
                if fail_at == 'replace':
                    with patch('pipeline.common.os.replace', side_effect=PermissionError('held output')):
                        with self.assertRaises(PermissionError):
                            execute()
                else:
                    with self.assertRaises(RuntimeError):
                        execute()
                self.assertEqual(output.read_bytes(), b'last-good')
                self.assertEqual(list(self.root.glob('.*.render-*.mp4')), [])
        with self.assertRaises(PipelineError):
            with output_transaction(output, overwrite=False):
                pass

    def test_windows_budget_counts_utf16_and_quoting(self):
        command = ['ffmpeg', '-i', 'long path/😀 clip.mp4']
        self.assertEqual(windows_command_units(command), len(subprocess.list2cmdline(command).encode('utf-16-le')) // 2 + 1)
        with self.assertRaises(PipelineError) as error:
            check_command(['ffmpeg', '😀' * 16000])
        self.assertEqual(error.exception.code, 'command_budget')

    def test_owned_child_cancellation(self):
        import time
        start = time.monotonic()
        with self.assertRaises(Cancelled):
            run([sys.executable, '-c', 'import time; time.sleep(30)'], cancel=lambda: time.monotonic() - start > .25)
        self.assertLess(time.monotonic() - start, 3)

    def test_lock_live_owner_and_os_release(self):
        path = self.root / 'operation.lock'
        code = 'from pathlib import Path; from pipeline.common import FileLock;\nwith FileLock(Path(__import__("sys").argv[1]), timeout=.15): print("owned")'
        env = {**os.environ, 'PYTHONPATH': str(ROOT / 'scripts')}
        with FileLock(path):
            result = subprocess.run([sys.executable, '-c', code, str(path)], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Another process owns', result.stderr)
        result = subprocess.run([sys.executable, '-c', code, str(path)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(path.exists())

    def test_config_rejects_invalid_timing_and_extensions(self):
        path = self.root / 'config.json'
        config = {'inbox_paths': ['inbox'], 'extensions': ['.mp4']}
        write_json(path, config)
        self.assertEqual(config_read(path)['inbox_paths'], [str(self.root / 'inbox')])
        for key, value in [('poll_seconds', 0), ('stable_seconds', -1), ('contact_sheet_frames', 0), ('max_attempts', True), ('extensions', ['mp4'])]:
            with self.subTest(key=key):
                write_json(path, {**config, key: value})
                with self.assertRaises(PipelineError):
                    config_read(path)

    def test_cancel_wins_over_ready_publication(self):
        store = JobStore(self.root)
        row = store.reserve('identity', self.root / 'source.mp4')
        store.update(row['id'], status='processing')
        store.request_cancel(row['id'])
        with self.assertRaises(Cancelled):
            store.finish_ready(row['id'], '2026-01-01T00:00:00+00:00')
        self.assertFalse((Path(row['job_path']) / 'READY.txt').exists())

    def test_caption_word_bounds_do_not_invent_removed_speech(self):
        transcript = {'segments': [{'start': 0, 'end': 3, 'text': 'one two three', 'words': [
            {'start': 0, 'end': 1, 'text': 'one'}, {'start': 1, 'end': 2, 'text': ' two'}, {'start': 2, 'end': 3, 'text': ' three'}]}]}
        cues = selected_cues(transcript, .5, 2.5, 4)
        self.assertEqual(cues, [{'start': 4.5, 'end': 5.5, 'text': 'two'}])
        transcript['segments'][0]['words'] = []
        self.assertEqual(selected_cues(transcript, .5, 2.5, 0), [])


class TTSContracts(unittest.TestCase):
    @staticmethod
    def response(data=b'\x01\x00' * 240, mime='audio/L16;codec=pcm;rate=24000', reason='STOP'):
        return NS(candidates=[NS(finish_reason=reason, content=NS(parts=[NS(text='metadata'), NS(inline_data=NS(data=data, mime_type=mime))]))])

    def test_valid_bytes_base64_and_multiple_parts(self):
        for data in (b'\x01\x00' * 240, base64.b64encode(b'\x01\x00' * 240).decode()):
            pcm, parameters, _ = extract_audio(self.response(data))
            self.assertEqual(len(pcm), 480)
            self.assertEqual(parameters, (24000, 1, 2))
        response = self.response()
        response.candidates[0].content.parts.append(response.candidates[0].content.parts[-1])
        self.assertEqual(len(extract_audio(response)[0]), 960)

    def test_abnormal_completion_never_accepts_usable_partial_audio(self):
        for reason in ('MAX_TOKENS', 'SAFETY', 'OTHER', None):
            with self.subTest(reason=reason), self.assertRaises(PipelineError):
                extract_audio(self.response(reason=reason))
        for response in (NS(candidates=[]), NS(candidates=[NS(finish_reason='STOP', content=NS(parts=[]))])):
            with self.assertRaises(PipelineError):
                extract_audio(response)

    def test_malformed_empty_and_mismatched_formats(self):
        for data, mime in [(b'', 'audio/L16;rate=24000'), ('not base64!', 'audio/L16;rate=24000'),
                           (b'odd', 'audio/L16;rate=24000'), (b'ab', 'audio/mpeg'), (b'ab', 'audio/pcm'),
                           (b'ab', 'audio/L16;rate=nan'), (b'ab', 'audio/L16;rate=24000;channels=0')]:
            with self.subTest(mime=mime, data=data), self.assertRaises(PipelineError):
                extract_audio(self.response(data, mime))
        response = self.response()
        response.candidates[0].content.parts += [NS(inline_data=NS(data=b'\0\0', mime_type='audio/L16;rate=16000'))]
        with self.assertRaises(PipelineError):
            extract_audio(response)

    def test_wav_and_publication_provenance_without_script_or_credentials(self):
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as wav:
            wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(32000); wav.writeframes(b'\0\0\0\0' * 100)
        raw = stream.getvalue()
        self.assertEqual(extract_audio(self.response(raw, 'audio/wav'))[1], (32000, 2, 2))
        with self.assertRaises(PipelineError):
            extract_audio(self.response(raw[:-1], 'audio/wav'))
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'voice.wav'
            output.write_bytes(b'old-good')
            with self.assertRaises(PipelineError):
                publish_response(self.response(reason='MAX_TOKENS'), output, model='test', voice='test', text='private-script')
            self.assertEqual(output.read_bytes(), b'old-good')
            result = publish_response(self.response(), output, model='test', voice='test', text='private-script')
            self.assertEqual(result['output_sha256'], file_hash(output))
            self.assertNotIn('private-script', Path(result['provenance']).read_text())
            self.assertNotIn('api_key', Path(result['provenance']).read_text().lower())


if __name__ == '__main__':
    unittest.main()
