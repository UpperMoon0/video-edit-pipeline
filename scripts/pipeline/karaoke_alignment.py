"""Optional local forced alignment; supplied lyrics remain the text authority."""
import copy
import re
import tempfile
from pathlib import Path
from .common import FileLock, PipelineError, file_hash, write_json
from .media import ffmpeg_args, run
from .karaoke import fail, load_project, lyrics_identity, source_info


def alignment_groups(cues):
    groups = []
    for cue in cues:
        if groups and cue['start'] - groups[-1][-1]['end'] < 1.5 and cue['end'] - groups[-1][0]['start'] <= 25:
            groups[-1].append(cue)
        else:
            groups.append([cue])
    return groups


def align(project, *, model='small', allow_download=False, device='cpu'):
    try:
        from faster_whisper import WhisperModel
        from faster_whisper.audio import decode_audio, pad_or_trim
        from faster_whisper.tokenizer import Tokenizer
    except ImportError as exc:
        raise PipelineError('karaoke_dependency', 'align', 'Install faster-whisper in an optional karaoke environment.') from exc
    if device not in ('cpu', 'cuda'):
        fail('karaoke_device', 'device', 'Alignment supports cpu or explicitly selected cuda.')
    path = Path(project).resolve()
    with FileLock(path.with_name('.' + path.name + '.align.lock')):
        path, spec, source = load_project(path, discard_timing=True)
        if spec.get('language', 'zh') != 'zh' or not spec['cues']:
            fail('karaoke_alignment_language', 'cues', 'Automatic alignment currently supports supplied Chinese lines; other languages can supply timed syllables.')
        _, _, _, _, duration = source_info(source)
        if spec['cues'][-1]['end'] > duration + .02:
            fail('karaoke_bounds', 'cues', 'Cue ranges extend beyond the video.')
        original_project = file_hash(path)
        source_hash = file_hash(source)
        engine = WhisperModel(model, device=device, compute_type='int8' if device == 'cpu' else 'float32',
                              local_files_only=not allow_download)
        tokenizer = Tokenizer(engine.hf_tokenizer, engine.model.is_multilingual, task='transcribe', language='zh')
        spec = copy.deepcopy(spec)
        # Re-alignment after a text change is explicit; loading must not silently discard stale timing.
        with tempfile.TemporaryDirectory(prefix='karaoke-align-') as directory:
            wav = Path(directory) / 'alignment.wav'
            run(ffmpeg_args() + ['-i', str(source), '-map', '0:a:0', '-ac', '1', '-ar', '16000', str(wav)])
            audio = decode_audio(str(wav))
            for group in alignment_groups(spec['cues']):
                a, b = max(0, group[0]['start'] - .15), min(duration, group[-1]['end'] + .15)
                lines = [re.sub(r'[^\u4e00-\u9fff]', '', c['text']) for c in group]
                if any(not s for s in lines):
                    fail('karaoke_alignment_text', 'cues', 'Chinese alignment needs a nonempty Chinese lyric line.')
                features = engine.feature_extractor(audio[round(a * 16000):round(b * 16000)])
                encoded = engine.encode(pad_or_trim(features))
                aligned = engine.find_alignment(tokenizer, [tokenizer.encode('，'.join(lines) + '。')], encoded,
                                                min(features.shape[-1], 3000))[0]
                chars = []
                for word in aligned:
                    text = re.findall(r'[\u4e00-\u9fff]', word['word'])
                    for j, char in enumerate(text):
                        chars.append((char, a + word['start'] + (word['end'] - word['start']) * j / len(text),
                                      a + word['start'] + (word['end'] - word['start']) * (j + 1) / len(text)))
                if ''.join(c[0] for c in chars) != ''.join(lines):
                    fail('karaoke_alignment_mismatch', 'cues', 'Aligned text does not match the supplied lyrics; no project was replaced.')
                offset = 0
                for cue, text in zip(group, lines):
                    tokens = chars[offset:offset + len(text)]
                    offset += len(text)
                    readings = cue.get('romanization')
                    if readings is None:
                        try:
                            from pypinyin import pinyin, Style
                        except ImportError as exc:
                            raise PipelineError('karaoke_dependency', 'romanization', 'Supply one romanization per character or install pypinyin.') from exc
                        readings = [s[0] for s in pinyin(text, style=Style.TONE)]
                    if len(readings) != len(text):
                        fail('karaoke_romanization_count', 'romanization', 'Supply one syllable per Chinese character.')
                    # Enforce representable positive intervals for occasional collapsed model tokens.
                    lo = max(round(tokens[0][1] * 100), round(cue['start'] * 100))
                    hi = min(round(tokens[-1][2] * 100), round(cue['end'] * 100))
                    if hi - lo < len(tokens):
                        fail('karaoke_alignment_collapsed', 'cues', 'Alignment collapsed this line; adjust its time window and retry.')
                    boundaries = [lo]
                    for j in range(1, len(tokens)):
                        boundaries.append(max(boundaries[-1] + 1, min(round(tokens[j][1] * 100), hi - (len(tokens) - j))))
                    boundaries.append(hi)
                    cue['syllables'] = [{'text': s, 'start': boundaries[j] / 100, 'end': boundaries[j + 1] / 100}
                                        for j, s in enumerate(readings)]
        if file_hash(path) != original_project or file_hash(source) != source_hash:
            fail('karaoke_alignment_changed', 'project', 'Project or media changed during alignment; no update was published.')
        spec['timing_source_sha256'] = source_hash
        spec['timing_lyrics_sha256'] = lyrics_identity(spec)
        write_json(path, spec)
    return {'project': str(path), 'cues': len(spec['cues']), 'model': model, 'source_sha256': source_hash,
            'review_required': 'Check sung syllables, pronunciation and repeated chorus boundaries.'}
