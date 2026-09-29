"""Frame-grid range previews with rebased source, event and fade phases."""
import copy
import math
import uuid
from pathlib import Path
from .common import PipelineError, same_file
from .timeline import load_timeline, normalize, frame_count
from .media import stream_duration
from .renderer import render


def preview_timeline(timeline, start, end, output, max_seconds=30):
    if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) for t in (start, end)):
        raise PipelineError('preview_range', 'start/end', 'Use finite range endpoints.')
    first, last = frame_count(start, timeline.fps), frame_count(end, timeline.fps)
    if not 0 <= first < last <= sum(timeline.frames) or float((last-first) / timeline.fps) > max_seconds:
        raise PipelineError('preview_range', 'start/end', f'Preview must select 1 frame to {max_seconds} seconds inside the edit.')
    if same_file(output, timeline.output) or any(same_file(output, p) for p in timeline.assets()):
        raise PipelineError('preview_output_alias', 'output', 'Preview cannot replace the final deliverable or an input.')
    start, end = float(first / timeline.fps), float(last / timeline.fps)
    spec = copy.deepcopy(timeline.spec)
    spec['output'] = str(Path(output).resolve())
    clips, offset = [], 0
    for clip, frames in zip(spec['clips'], timeline.frames):
        lo, hi = max(first, offset), min(last, offset + frames)
        if hi > lo:
            if clip['type'] == 'video':
                clip['in'] += float((lo - offset) / timeline.fps)
            clip['duration'] = float((hi - lo) / timeline.fps)
            clips.append(clip)
        offset += frames
    spec['clips'] = clips
    phases = []
    groups = [('overlays', spec.get('overlays', [])), ('titles', spec.get('titles', [])),
              ('music', spec['audio'].get('music', [])), ('sfx', spec['audio'].get('sfx', []))]
    for kind, group in groups:
        kept = []
        for event in group:
            a, b = event['start'], event.get('end', event['start'] + event.get('duration', 0))
            lo, hi = max(start, a), min(end, b)
            if hi <= lo:
                continue
            original_duration, phase = b - a, lo - a
            event['start'] = lo - start
            if 'end' in event:
                event['end'] = hi - start
            else:
                event['duration'] = hi - lo
            if kind in ('music', 'sfx'):
                event['source_in'] = event.get('source_in', 0) + phase
            if kind != 'titles':
                default_in = 1 if kind == 'music' else .5 if kind == 'overlays' else 0
                default_out = 1 if kind == 'music' else .5 if kind == 'overlays' else .05
                data = {'_original_duration': original_duration, '_fade_phase': phase,
                        'fade_in': event.get('fade_in', min(default_in, original_duration / 2)),
                        'fade_out': event.get('fade_out', min(default_out, original_duration / 2))}
                phases.append((kind, len(kept), data))
                event['fade_in'] = event['fade_out'] = 0  # validate cropped range, then attach original phase
            kept.append(event)
        group[:] = kept
    audio = spec['audio']
    if audio.get('voiceover'):
        previous_start = audio.get('voiceover_start', 0)
        audio['voiceover_start'] = max(0, previous_start - start)
        audio['voiceover_source_in'] = audio.get('voiceover_source_in', 0) + max(0, start - previous_start)
        info = timeline.media[str(timeline.asset(audio['voiceover']))]
        stream = next(s for s in info['streams'] if s['codec_type'] == 'audio')
        duration = stream_duration(stream, info)
        if previous_start >= end or (duration is not None and audio['voiceover_source_in'] >= duration):
            for key in ('voiceover', 'voiceover_start', 'voiceover_source_in', 'voiceover_volume', 'ducking'):
                audio.pop(key, None)
            if spec.get('captions', {}).get('kind') == 'narration':
                spec.pop('captions')
    # Drop exhausted external tracks; the timeline bed still supplies silence.
    for kind in ('music', 'sfx'):
        for event in audio.get(kind, []):
            info = timeline.media[str(timeline.asset(event['source']))]
            stream = next(s for s in info['streams'] if s['codec_type'] == 'audio')
            duration = stream_duration(stream, info)
            if duration is not None and event.get('source_in', 0) >= duration:
                event['source_in'] = 0
                event['volume'] = 0
    ratio = min(1, 640 / spec['video']['width'])
    spec['video']['width'] = max(16, round(spec['video']['width'] * ratio / 2) * 2)
    spec['video']['height'] = max(16, round(spec['video']['height'] * ratio / 2) * 2)
    for kind in ('overlays', 'titles'):
        for event in spec.get(kind, []):
            for axis in ('x', 'y'):
                if isinstance(event.get(axis), (int, float)):
                    event[axis] *= ratio
            if kind == 'overlays':
                event['width'] = max(1, round(event.get('width', min(800, timeline.spec['video']['width'])) * ratio))
            else:
                event['size'] = max(8, round(event.get('size', 48) * ratio))
    spec['encode'] = {'preset': 'ultrafast', 'crf': 24}
    spec.pop('qa', None)  # whole-program black/silence/loudness thresholds are not range thresholds
    spec.setdefault('metadata', {})['preview_of'] = {'revision': timeline.spec['revision'], 'start': start, 'end': end}
    result = normalize(spec, timeline.base, path=timeline.path, media=True)
    for kind, index, data in phases:
        target = result.spec[kind] if kind in ('overlays', 'titles') else result.spec['audio'][kind]
        target[index].update(data)
    if result.spec.get('captions'):
        from .captions import retime
        if not retime(result):
            result.spec.pop('captions')
    return result


def preview(path, start, end, output=None):
    timeline = load_timeline(path, media=True)
    output = Path(output).resolve() if output else timeline.output.parent / 'previews' / (uuid.uuid4().hex + '.mp4')
    result = preview_timeline(timeline, start, end, output)
    return render(result, cache_enabled=False, overwrite=False)
