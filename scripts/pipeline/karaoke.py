"""Reusable local karaoke projects, subtitle design and QA-gated delivery."""
from __future__ import annotations
import math
import re
import uuid
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlparse

from jsonschema import Draft202012Validator
from .captions import timestamp
from .common import (PipelineError, FileLock, atomic_write, digest, file_hash,
                     output_transaction, read_json, write_json)
from .media import ffmpeg_args, probe, run, stream_duration
from .qa import inspect_output, require_pass

NUMBER = {'type': 'number', 'minimum': 0}
TOKEN = {'type': 'object', 'additionalProperties': False,
         'required': ['text', 'start', 'end'],
         'properties': {'text': {'type': 'string', 'minLength': 1}, 'start': NUMBER, 'end': NUMBER}}
SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'type': 'object', 'additionalProperties': False,
    'required': ['version', 'title', 'source', 'cues', 'credits'],
    'properties': {
        'version': {'const': 1}, 'title': {'type': 'string', 'minLength': 1, 'maxLength': 100},
        'source': {'type': 'string', 'minLength': 1},
        'language': {'type': 'string', 'enum': ['zh', 'ja', 'en']},
        'intro': {'type': 'string'},
        'style': {'type': 'object', 'additionalProperties': False, 'properties': {
            'font': {'type': 'string', 'minLength': 1},
            'translation_font': {'type': 'string', 'minLength': 1},
            'font_size': {'type': 'integer', 'minimum': 24, 'maximum': 64},
            'translation_size': {'type': 'integer', 'minimum': 20, 'maximum': 46},
            'panel': {'type': 'boolean'}}},
        'credits': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['role', 'name', 'url'],
            'properties': {'role': {'enum': ['animation_creator', 'original_video', 'music', 'remix', 'reupload']},
                           'name': {'type': 'string', 'minLength': 1}, 'url': {'type': 'string', 'minLength': 1}}}},
        'cues': {'type': 'array', 'maxItems': 10000, 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['text', 'translation', 'start', 'end'],
            'properties': {'text': {'type': 'string', 'minLength': 1},
                'translation': {'type': 'string', 'minLength': 1}, 'start': NUMBER, 'end': NUMBER,
                'romanization': {'type': 'array', 'minItems': 1, 'items': {'type': 'string', 'minLength': 1}},
                'syllables': {'type': 'array', 'minItems': 1, 'items': TOKEN}}}},
        'timing_source_sha256': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
        'timing_lyrics_sha256': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
    }}


def fail(code, field, message):
    raise PipelineError(code, field, message)


def lyrics_identity(spec):
    return digest([{k: c[k] for k in ('text', 'start', 'end', 'romanization') if k in c}
                   for c in spec['cues']])


def ass_text(text):
    # Plain text only: prevent lyrics/credits becoming libass override commands.
    return text.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\r', '').replace('\n', ' ')


def ass_time(value):
    n = round(value * 100)
    return f'{n // 360000}:{n // 6000 % 60:02}:{n // 100 % 60:02}.{n % 100:02}'


def source_info(path, *, frames=False):
    info = probe(path, count_frames=frames)
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
    if not video or not audio:
        fail('karaoke_media', 'source', 'Karaoke requires both a video and an audio stream.')
    if video['width'] * 9 != video['height'] * 16:
        fail('karaoke_aspect', 'source', 'The premium preset currently supports 16:9 landscape media.')
    duration = stream_duration(video, info)
    if duration is None:
        fail('karaoke_duration', 'source', 'Video duration is unavailable.')
    average = Fraction(video.get('avg_frame_rate', '0/1'))
    fps = Fraction(video.get('r_frame_rate', str(average)))
    # MP4 duration/time-base quantization can make avg_frame_rate slightly differ
    # from a valid nominal CFR rate. Permit at most one frame over the source span.
    if min(fps, average) <= 0 or abs(float(average - fps)) * duration > 1:
        fail('karaoke_rate', 'source', 'Use a constant-frame-rate source before karaoke delivery.')
    return info, video, audio, fps, duration


def load_project(path, *, timed=False, discard_timing=False):
    path = Path(path).resolve()
    spec = read_json(path)
    errors = sorted(Draft202012Validator(SCHEMA).iter_errors(spec), key=lambda e: str(e.path))
    if errors:
        fail('karaoke_schema', '.'.join(map(str, errors[0].path)), errors[0].message)
    if discard_timing:
        for cue in spec['cues']:
            cue.pop('syllables', None)
        spec.pop('timing_source_sha256', None)
        spec.pop('timing_lyrics_sha256', None)
    source = (path.parent / spec['source']).resolve()
    if not source.is_file():
        fail('karaoke_source', 'source', 'Source media does not exist.')
    previous = 0
    for i, cue in enumerate(spec['cues']):
        a, b = cue['start'], cue['end']
        if any(isinstance(t, bool) or not math.isfinite(t) for t in (a, b)) or a < previous or b <= a:
            fail('karaoke_order', f'cues.{i}', 'Cue ranges must be finite, positive and nonoverlapping.')
        if round(b * 100) <= round(a * 100):
            fail('karaoke_resolution', f'cues.{i}', 'Cue is shorter than ASS centisecond resolution.')
        previous = b
        syllables = cue.get('syllables', [])
        if timed and not syllables:
            fail('karaoke_untimed', f'cues.{i}', 'Supply timed syllables or run the optional align stage first.')
        boundary = a
        for j, s in enumerate(syllables):
            lo, hi = s['start'], s['end']
            if any(isinstance(t, bool) or not math.isfinite(t) for t in (lo, hi)) or lo < boundary - 1e-6 or lo < a or hi > b + 1e-6 or hi <= lo:
                fail('karaoke_syllables', f'cues.{i}.syllables.{j}', 'Syllables must be ordered, positive and contained in their cue.')
            if round(hi * 100) <= round(lo * 100):
                fail('karaoke_resolution', f'cues.{i}.syllables.{j}', 'Syllable is shorter than ASS centisecond resolution.')
            boundary = hi
    for c in spec['credits']:
        url = urlparse(c['url'])
        if url.scheme not in ('https', 'http') or not url.netloc or url.username or url.password:
            fail('karaoke_credit_url', 'credits', 'Credits need a public HTTP(S) source URL without credentials.')
    if timed and not spec['cues']:
        fail('karaoke_empty', 'cues', 'Add the supplied lyrics, translation and source-time cues first.')
    if timed and 'timing_lyrics_sha256' in spec and spec['timing_lyrics_sha256'] != lyrics_identity(spec):
        fail('karaoke_stale_timing', 'cues', 'Lyrics or cue ranges changed after alignment; realign or review manual timing and remove the old timing hashes.')
    return path, spec, source


def initialize(source, destination, title):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    source_info(source)
    if not title or len(title) > 100:
        fail('karaoke_title', 'title', 'Supply a title of 1–100 characters.')
    with output_transaction(destination, [source], overwrite=False) as temp:
        write_json(temp, {'version': 1, 'title': title, 'source': str(source), 'language': 'zh',
                         'style': {'font': 'Arial', 'translation_font': 'Arial', 'panel': True},
                         'credits': [], 'cues': []})
    return {'project': str(destination), 'status': 'needs_lyrics_and_credits'}


def panel_ranges(cues):
    result = []
    for c in cues:
        a, b = max(0, c['start'] - .2), c['end'] + .2
        if result and a - result[-1][1] < .75:
            result[-1][1] = b
        else:
            result.append([a, b])
    return result


def description(spec, instrumental=False):
    sections = [spec.get('intro') or spec['title']]
    if instrumental:
        sections.append('Vocals reduced for karaoke.')
    labels = {'animation_creator': 'ORIGINAL ANIMATION CREATOR', 'original_video': 'ORIGINAL VIDEO',
              'music': 'MUSIC CREDIT', 'remix': 'REMIX CREDIT', 'reupload': 'SOURCE REUPLOAD (not the original creator)'}
    for role, label in labels.items():
        entries = [f'{c["name"]}\n{c["url"]}' for c in spec['credits'] if c['role'] == role]
        if entries:
            sections.append(label + '\n' + '\n'.join(entries))
    result = '\n\n'.join(sections) + '\n'
    if len(result) > 5000:
        fail('karaoke_description', 'credits', 'Description exceeds YouTube\'s 5000-character limit.')
    return result


def subtitle_documents(spec):
    style = spec.get('style', {})
    font = style.get('font', 'Arial')
    english = style.get('translation_font', 'Arial')
    if any(re.search(r'[,\r\n{}\\]', f) for f in (font, english)):
        fail('karaoke_font', 'style', 'Font family must be a plain font name.')
    size, esize = style.get('font_size', 54), style.get('translation_size', 38)
    header = f'''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pinyin,{font},{size},&H0086D0EF,&H00E8EBF0,&H8010141A,&HFF000000,0,0,0,0,100,100,0.4,0,1,0.7,0,2,110,110,96,1
Style: English,{english},{esize},&H00DDD4CC,&H00DDD4CC,&H8010141A,&HFF000000,0,0,0,0,100,100,0.2,0,1,0.5,0,2,110,110,174,1
Style: Panel,Arial,1,&H001F140D,&H001F140D,&H001F140D,&HFF000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    rows, srt = [], []
    def row(layer, a, b, name, text):
        rows.append(f'Dialogue: {layer},{ass_time(a)},{ass_time(b)},{name},,0,0,0,,{text}')
    if style.get('panel', True):
        shape = 'm 106 820 l 1814 820 b 1828 820 1840 832 1840 846 l 1840 1002 b 1840 1016 1828 1028 1814 1028 l 106 1028 b 92 1028 80 1016 80 1002 l 80 846 b 80 832 92 820 106 820'
        for a, b in panel_ranges(spec['cues']):
            row(0, a, b, 'Panel', r'{\an7\pos(0,9)\p1\bord0\blur14\1c&H000000&\1a&H90&\fad(200,200)}' + shape)
            row(1, a, b, 'Panel', r'{\an7\pos(0,0)\p1\bord0\1a&H12&\fad(200,200)}' + shape)
            row(1, a, b, 'Panel', r'{\an7\pos(0,0)\p1\bord0\1c&H86D0EF&\1a&H40&\fad(200,200)}m 936 841 l 984 841 l 984 844 l 936 844')
    warnings = []
    for i, c in enumerate(spec['cues'], 1):
        a, b = round(c['start'] * 100), round(c['end'] * 100)
        cursor, body = a, ''
        for s in c['syllables']:
            lo, hi = round(s['start'] * 100), round(s['end'] * 100)
            if lo > cursor:
                body += '{\\k' + str(lo - cursor) + '}\u200b'
            body += '{\\kf' + str(hi - lo) + '}' + ass_text(s['text']) + ' '
            cursor = hi
        row(3, c['start'], c['end'], 'Pinyin', body.rstrip())
        row(2, c['start'], c['end'], 'English', ass_text(c['translation']))
        roman = ' '.join(s['text'] for s in c['syllables'])
        srt.append(f'{i}\n{timestamp(c["start"])} --> {timestamp(c["end"])}\n{c["translation"]}\n{roman}\n')
        if len(roman) > 70 or len(c['translation']) > 95:
            warnings.append(f'Cue {i} is long; split the phrase or review a preview for overflow.')
    roles = {c['role'] for c in spec['credits']}
    if 'music' not in roles or not roles.intersection({'animation_creator', 'original_video'}):
        warnings.append('Verify original music and visual creator credits before publication; a reupload alone is insufficient attribution.')
    return header + '\n'.join(rows) + '\n', '\n'.join(srt), warnings


def build(project):
    path, spec, source = load_project(project, timed=True)
    _, _, _, _, duration = source_info(source)
    source_hash = file_hash(source)
    if spec.get('timing_source_sha256', source_hash) != source_hash:
        fail('karaoke_stale_source', 'source', 'Source media changed after alignment.')
    if spec['cues'][-1]['end'] > duration + .02:
        fail('karaoke_bounds', 'cues', 'Lyrics extend beyond the video.')
    ass, srt, warnings = subtitle_documents(spec)
    identity = digest({'project': spec, 'source_sha256': source_hash, 'design_version': 1})
    bundle = path.parent / '.karaoke' / identity
    with FileLock(path.with_name('.' + path.name + '.build.lock')):
        for name, value in [('subtitles.ass', ass), ('subtitles.srt', srt),
                            ('description.txt', description(spec)), ('description-instrumental.txt', description(spec, True))]:
            atomic_write(bundle / name, value.encode('utf-8-sig' if name.endswith('.ass') else 'utf-8'))
        result = {'version': 1, 'identity': identity, 'source': str(source), 'source_sha256': source_hash,
                  'project': str(path), 'bundle': str(bundle), 'ass': str(bundle / 'subtitles.ass'),
                  'srt': str(bundle / 'subtitles.srt'), 'warnings': warnings, 'cues': len(spec['cues'])}
        write_json(bundle / 'build.json', result)
    return result


def render(project, output, *, encoder='libx264', start=None, duration=None):
    if encoder not in ('libx264', 'h264_nvenc'):
        fail('karaoke_encoder', 'encoder', 'Choose libx264 or explicitly request h264_nvenc.')
    built = build(project)
    source = Path(built['source'])
    bundle = Path(built['bundle'])
    _, video, _, fps, length = source_info(source, frames=True)
    if start is not None or duration is not None:
        if start is None or duration is None or not all(math.isfinite(x) for x in (start, duration)) or start < 0 or duration <= 0 or start + duration > length + .001:
            fail('karaoke_preview_range', 'start', 'Supply a finite start and duration within the source.')
        frames = round(duration * fps)
    else:
        start = 0
        frames = int(video.get('nb_read_frames', 0))
    if frames < 1:
        fail('karaoke_frames', 'source', 'No renderable frames in the selected range.')
    output = Path(output).resolve()
    with output_transaction(output, [source, project, built['ass'], built['srt']]) as temp:
        command = ffmpeg_args() + ['-i', str(source), '-ss', str(start), '-vf', 'ass=subtitles.ass',
            '-map', '0:v:0', '-map', '0:a:0', '-r', str(fps), '-frames:v', str(frames),
            '-t', str(float(frames / fps)), '-c:v', encoder]
        command += ['-preset', 'veryfast', '-crf', '18'] if encoder == 'libx264' else ['-preset', 'p5', '-rc', 'vbr', '-cq', '19', '-b:v', '0']
        command += ['-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-af', 'apad', '-movflags', '+faststart', str(temp)]
        run(command, cwd=bundle)
        report = inspect_output(temp, fps, frames)
        require_pass(report)
        if file_hash(source) != built['source_sha256']:
            fail('karaoke_source_changed', 'source', 'Source changed during rendering.')
        write_json(bundle / ('preview-qa-' + uuid.uuid4().hex + '.json' if duration is not None else 'render-qa.json'), report)
    return {'output': str(output), 'build': built, 'qa': report}


def video_packet_hash(path):
    return run(ffmpeg_args() + ['-i', str(path), '-map', '0:v:0', '-c:v', 'copy',
                                '-f', 'hash', '-hash', 'sha256', '-']).stdout.strip()


def remux(video_path, audio_path, output):
    video_path, audio_path, output = map(lambda p: Path(p).resolve(), (video_path, audio_path, output))
    _, video, _, fps, duration = source_info(video_path, frames=True)
    audio_info = probe(audio_path)
    audio = next((s for s in audio_info['streams'] if s['codec_type'] == 'audio'), None)
    ad = stream_duration(audio, audio_info) if audio else None
    if ad is None or abs(ad - duration) > .1:
        fail('karaoke_audio_length', 'audio', 'Replacement audio must match picture duration within 0.1 seconds; align it first.')
    hashes = {str(p): file_hash(p) for p in (video_path, audio_path)}
    packet_hash = video_packet_hash(video_path)
    with output_transaction(output, [video_path, audio_path]) as temp:
        run(ffmpeg_args() + ['-i', str(video_path), '-i', str(audio_path), '-map', '0:v:0', '-map', '1:a:0',
            '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-af', 'apad', '-t', str(duration), '-movflags', '+faststart', str(temp)])
        report = inspect_output(temp, fps, int(video['nb_read_frames']))
        require_pass(report)
        report['picture_packets_unchanged'] = video_packet_hash(temp) == packet_hash
        if not report['picture_packets_unchanged'] or any(file_hash(p) != h for p, h in hashes.items()):
            fail('karaoke_remux_identity', 'output', 'Picture packets or input files changed during the audio-only export.')
    return {'output': str(output), 'qa': report}
