"""Structural validation, rational frame timing and media preflight."""
from __future__ import annotations
import copy
import math
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from jsonschema import Draft202012Validator
from .common import PipelineError, read_json, resolve, reject_alias
from .media import probe, stream_duration
from .schema import SCHEMA


def rate(value):
    try:
        if isinstance(value, bool):
            raise ValueError('boolean frame rate')
        fps = Fraction(str(value))
        if not 0 < fps <= 240:
            raise ValueError('frame rate must be > 0 and <= 240')
        return fps
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise PipelineError('invalid_fps', 'video.fps', str(exc), 'Use 30, 29.97, or "30000/1001".') from exc


def frame_count(seconds, fps):
    value = Fraction(str(seconds)) * fps
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def finite_tree(value, field_name='$'):
    if isinstance(value, float) and not math.isfinite(value):
        raise PipelineError('nonfinite', field_name, 'All numbers must be finite.')
    if isinstance(value, dict):
        for key, item in value.items():
            finite_tree(item, field_name + '.' + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            finite_tree(item, f'{field_name}[{index}]')


@dataclass
class Timeline:
    spec: dict
    base: Path
    path: Path | None
    fps: Fraction
    frames: list[int]
    media: dict = field(default_factory=dict)

    @property
    def duration(self):
        return float(Fraction(sum(self.frames), 1) / self.fps)

    @property
    def output(self):
        return resolve(self.base, self.spec['output'])

    def asset(self, value):
        return resolve(self.base, value)

    def assets(self):
        values = [c['source'] for c in self.spec['clips']]
        values += [c['transcript'] for c in self.spec['clips'] if c.get('transcript')]
        values += [o['source'] for o in self.spec.get('overlays', [])]
        values += [t['font'] for t in self.spec.get('titles', []) if t.get('font')]
        audio = self.spec.get('audio', {})
        if audio.get('voiceover'):
            values.append(audio['voiceover'])
        for kind in ('music', 'sfx'):
            values += [t['source'] for t in audio.get(kind, [])]
        if self.spec.get('captions', {}).get('transcript'):
            values.append(self.spec['captions']['transcript'])
        return sorted({self.asset(v) for v in values}, key=str)


def load_timeline(path, *, media=False):
    path = Path(path).resolve()
    return normalize(read_json(path), path.parent, path=path, media=media)


def normalize(raw, base, *, path=None, media=False):
    finite_tree(raw)
    if isinstance(raw, dict) and 'cuts' in raw and 'clips' not in raw:
        raise PipelineError('scaffold', 'cuts', 'This is an editorial scaffold, not a renderable timeline.', 'Run pipeline.py convert-scaffold with a NEW destination.')
    errors = sorted(Draft202012Validator(SCHEMA).iter_errors(raw), key=lambda e: str(list(e.path)))
    if errors:
        error = errors[0]
        raise PipelineError('schema', '.'.join(map(str, error.path)) or '$', error.message, 'See schemas/timeline-v1.schema.json.')
    spec = copy.deepcopy(raw)
    spec.setdefault('version', 1)
    spec.setdefault('revision', 0)
    video = spec.setdefault('video', {})
    video.setdefault('width', 1920)
    video.setdefault('height', 1080)
    fps = rate(video.get('fps', 30))
    video['fps'] = str(fps)
    for axis in ('width', 'height'):
        if video[axis] % 2:
            raise PipelineError('dimensions', 'video.' + axis, 'H.264 yuv420p dimensions must be even.')
    ids, frames = set(), []
    for i, clip in enumerate(spec['clips']):
        clip.setdefault('id', f'clip-{i + 1:04d}')
        if clip['id'] in ids:
            raise PipelineError('duplicate_id', f'clips.{i}.id', 'Clip IDs must be unique.')
        ids.add(clip['id'])
        clip.setdefault('type', 'video')
        clip.setdefault('in', 0)
        clip.setdefault('audio', {'mode': 'mute'})
        clip['audio'].setdefault('mode', 'mute')
        count = frame_count(clip['duration'], fps)
        if count < 1:
            raise PipelineError('subframe_clip', f'clips.{i}.duration', 'Clip rounds to zero frames.')
        frames.append(count)
        clip['duration'] = float(Fraction(count, 1) / fps)
        if clip['type'] == 'image' and clip['in'] != 0:
            raise PipelineError('image_seek', f'clips.{i}.in', 'Still images require in=0.')
    timeline = Timeline(spec, Path(base).resolve(), path, fps, frames)
    if timeline.duration > 86400:
        raise PipelineError('duration_limit', 'clips', 'Timeline exceeds the 24-hour supported limit.')
    if timeline.output.suffix.lower() not in ('.mp4', '.mov', '.mkv'):
        raise PipelineError('container', 'output', 'Supported containers: MP4, MOV, MKV.')
    for group in ('overlays', 'titles'):
        for i, item in enumerate(spec.get(group, [])):
            check_range(item, timeline.duration, f'{group}.{i}')
    audio = spec.setdefault('audio', {})
    for kind in ('music', 'sfx'):
        for i, item in enumerate(audio.get(kind, [])):
            dur = item['end'] - item['start'] if kind == 'music' else item['duration']
            check_range({**item, 'duration': dur}, timeline.duration, f'audio.{kind}.{i}')
    if audio.get('voiceover_start', 0) >= timeline.duration:
        raise PipelineError('time_range', 'audio.voiceover_start', 'Narration starts beyond the edit.')
    if audio.get('ducking', {}).get('enabled') and not audio.get('voiceover'):
        raise PipelineError('ducking_voice', 'audio.ducking', 'Ducking requires narration.')
    captions = spec.get('captions', {})
    if captions.get('kind') == 'narration' and (not audio.get('voiceover') or not captions.get('transcript')):
        raise PipelineError('caption_source', 'captions', 'Narration captions require narration audio and its transcript.')
    for asset in timeline.assets():
        if not asset.is_file():
            raise PipelineError('missing_asset', str(asset), 'Asset does not exist.', 'Paths are relative to the timeline JSON.')
    reject_alias(timeline.output, timeline.assets() + ([path] if path else []))
    if media:
        preflight(timeline)
    return timeline


def check_range(item, duration, field_name):
    if item['duration'] <= 0 or item['start'] + item['duration'] > duration + 1e-6:
        raise PipelineError('time_range', field_name, 'Range must be positive and contained in the edit.')
    for fade in ('fade_in', 'fade_out'):
        if item.get(fade, 0) > item['duration'] / 2:
            raise PipelineError('fade_range', field_name + '.' + fade, 'Each fade must be <= half the track duration.')


def preflight(timeline):
    def get(value, kind, field_name):
        path = timeline.asset(value)
        if str(path) not in timeline.media:
            timeline.media[str(path)] = probe(path)
        info = timeline.media[str(path)]
        streams = [s for s in info['streams'] if s['codec_type'] == kind]
        if not streams:
            raise PipelineError('missing_stream', field_name, f'{path} has no {kind} stream.')
        return info, streams

    for i, clip in enumerate(timeline.spec['clips']):
        info, streams = get(clip['source'], 'video', f'clips.{i}.source')
        stream = streams[0]
        if clip['type'] == 'video':
            duration = stream_duration(stream, info)
            origin = float(info.get('format', {}).get('start_time', 0))
            first = max(0, float(stream.get('start_time', origin)) - origin)
            if duration is None:
                raise PipelineError('unknown_video_duration', f'clips.{i}.source', 'Cannot establish a usable video range.', 'Remux/probe the asset first.')
            try:
                end_tolerance = max(1e-6, float(Fraction(stream.get('time_base', '1/1000000'))))
            except (ValueError, ZeroDivisionError):
                end_tolerance = 1e-6
            if clip['in'] < first - 1e-6 or clip['in'] >= first + duration or clip['in'] + clip['duration'] > first + duration + end_tolerance:
                raise PipelineError('source_range', f'clips.{i}', f'Requested {clip["in"]:.6f}..{clip["in"] + clip["duration"]:.6f}; usable video range {first:.6f}..{first + duration:.6f}.',
                    'Trim the cut to available footage; implicit freeze/loop padding is not supported.')
        policy = clip['audio']
        audio = [s for s in info['streams'] if s['codec_type'] == 'audio']
        if policy['mode'] == 'preserve' and policy.get('stream', 0) >= len(audio) and (audio or policy.get('stream', 0) != 0):
            raise PipelineError('audio_stream', f'clips.{i}.audio.stream', 'Selected audio stream does not exist.')
    for i, overlay in enumerate(timeline.spec.get('overlays', [])):
        get(overlay['source'], 'video', f'overlays.{i}.source')
    audio = timeline.spec['audio']
    if audio.get('voiceover'):
        info, streams = get(audio['voiceover'], 'audio', 'audio.voiceover')
        duration = stream_duration(streams[0], info)
        if duration is not None and audio.get('voiceover_source_in', 0) >= duration:
            raise PipelineError('source_range', 'audio.voiceover_source_in', 'Narration seek is at or beyond EOF.')
    for kind in ('music', 'sfx'):
        for i, track in enumerate(audio.get(kind, [])):
            info, streams = get(track['source'], 'audio', f'audio.{kind}.{i}.source')
            duration = stream_duration(streams[0], info)
            if duration is not None and track.get('source_in', 0) >= duration:
                raise PipelineError('source_range', f'audio.{kind}.{i}.source_in', 'Audio seek is at or beyond EOF.')
    return timeline
