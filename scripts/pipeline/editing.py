"""Optimistic, reversible timeline edits on one rational frame grid."""
import copy
import uuid
from pathlib import Path
from .common import FileLock, PipelineError, read_json, write_json, file_hash, digest
from .timeline import load_timeline, normalize, frame_count, rate


def _clip_index(spec, clip_id):
    matches = [i for i, c in enumerate(spec['clips']) if c['id'] == clip_id]
    if not matches:
        raise PipelineError('unknown_clip', 'clip_id', f'No clip with ID {clip_id}.')
    return matches[0]


def _finite_number(value, field_name):
    import math
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PipelineError('operation_parameter', field_name, 'Expected a finite number.')
    return value


def _shift_events(spec, start, removed):
    """Ripple only unambiguously associated events; refuse events crossing cuts."""
    end = start + removed
    groups = [spec.get('overlays', []), spec.get('titles', [])]
    audio = spec.get('audio', {})
    groups += [audio.get('music', []), audio.get('sfx', [])]
    for group in groups:
        keep = []
        for event in group:
            a = event['start']
            b = event.get('end', a + event.get('duration', 0))
            if a >= start - 1e-7 and b <= end + 1e-7:
                continue
            if a < end - 1e-7 and b > start + 1e-7:
                raise PipelineError('ripple_crossing_event', 'events', 'An audio/graphic event crosses the removed range.',
                    'Split or reposition that event explicitly before rippling; the editor will not silently retime fades or narration.')
            if a >= end - 1e-7:
                event['start'] -= removed
                if 'end' in event:
                    event['end'] -= removed
            keep.append(event)
        group[:] = keep
    if audio.get('voiceover'):
        raise PipelineError('ripple_narration', 'audio.voiceover', 'Ripple removal with external narration requires explicit narration editing first.')


def apply_operation(timeline, operation):
    spec = copy.deepcopy(timeline.spec)
    name = operation.get('op')
    allowed = {'split': {'op', 'clip_id', 'at'}, 'trim': {'op', 'clip_id', 'in', 'duration', 'ripple'},
        'reorder': {'op', 'clip_ids'}, 'ripple-delete': {'op', 'clip_id'}, 'undo': {'op', 'revision'}}
    if name not in allowed or operation.keys() - allowed[name]:
        raise PipelineError('operation_schema', 'operation', 'Unsupported operation or fields.')
    if name == 'reorder':
        ids = operation.get('clip_ids')
        known = [c['id'] for c in spec['clips']]
        if not isinstance(ids, list) or len(ids) != len(known) or set(ids) != set(known):
            raise PipelineError('operation_schema', 'clip_ids', 'Supply an exact permutation of every clip ID.')
        spec['clips'] = [next(c for c in spec['clips'] if c['id'] == id_) for id_ in ids]
    elif name in ('split', 'trim', 'ripple-delete'):
        index = _clip_index(spec, operation.get('clip_id'))
        clip = spec['clips'][index]
        offset = sum(c['duration'] for c in spec['clips'][:index])
        if name == 'split':
            at = _finite_number(operation.get('at'), 'at')
            frames = frame_count(at, timeline.fps)
            if not 0 < frames < timeline.frames[index]:
                raise PipelineError('split_range', 'at', 'Split must be strictly inside the clip.')
            duration = float(frames / timeline.fps)
            right = copy.deepcopy(clip)
            right['id'] = clip['id'] + '-split-' + uuid.uuid4().hex[:8]
            right['in'] += duration if clip['type'] == 'video' else 0
            right['duration'] -= duration
            clip['duration'] = duration
            spec['clips'].insert(index + 1, right)
        elif name == 'trim':
            new_in = _finite_number(operation.get('in'), 'in')
            duration = _finite_number(operation.get('duration'), 'duration')
            new_frames = frame_count(duration, timeline.fps)
            if new_in < 0 or new_frames < 1:
                raise PipelineError('trim_range', 'trim', 'Require nonnegative source in and at least one frame.')
            duration = float(new_frames / timeline.fps)
            difference = clip['duration'] - duration
            if abs(difference) > 1e-7:
                if not operation.get('ripple') or difference < 0:
                    raise PipelineError('trim_timing', 'duration', 'Duration changes require ripple=true and may only shorten the clip.',
                        'Equal-duration slip edits keep all timeline events unchanged.')
                _shift_events(spec, offset + duration, difference)
            clip.update({'in': new_in, 'duration': duration})
        else:
            if len(spec['clips']) == 1:
                raise PipelineError('empty_timeline', 'clips', 'Cannot remove the only clip.')
            _shift_events(spec, offset, clip['duration'])
            spec['clips'].pop(index)
    else:
        raise PipelineError('undo_context', 'op', 'Undo must be applied through the revision-aware editor.')
    return normalize(spec, timeline.base, path=timeline.path, media=True)


def edit_timeline(path, expected_revision, operation):
    path = Path(path).resolve()
    with FileLock(path.with_name('.' + path.name + '.edit.lock'), timeout=30):
        current = load_timeline(path, media=True)
        if current.spec['revision'] != expected_revision:
            raise PipelineError('stale_revision', 'expected_revision', f'Current revision is {current.spec["revision"]}, not {expected_revision}.', 'Read the latest timeline and rebase the edit.')
        history = path.parent / '.timeline-history' / digest(str(path))[:16]
        if operation.get('op') == 'undo':
            revision = operation.get('revision')
            if isinstance(revision, bool) or not isinstance(revision, int) or not 0 <= revision < expected_revision:
                raise PipelineError('undo_revision', 'revision', 'Choose an earlier stored revision.')
            snapshot = read_json(history / (str(revision) + '.json'))
            updated = normalize(snapshot['timeline'], current.base, path=path, media=True)
        else:
            updated = apply_operation(current, operation)
        snapshot_path = history / (str(expected_revision) + '.json')
        if snapshot_path.exists():
            old = read_json(snapshot_path)
            if old['timeline'] != current.spec:
                raise PipelineError('history_conflict', 'revision', 'Existing history does not match the current revision; no overwrite performed.')
        else:
            write_json(snapshot_path, {'version': 1, 'timeline': current.spec, 'file_sha256': file_hash(path), 'next_operation': operation})
        updated.spec['revision'] = expected_revision + 1
        write_json(path, updated.spec)
        return {'version': 1, 'revision': updated.spec['revision'], 'timeline': updated.spec, 'history': str(history)}


def convert_scaffold(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    raw = read_json(source)
    if destination.exists() or destination == source:
        raise PipelineError('destination_exists', 'destination', 'Scaffold conversion requires a new destination; editorial work is never overwritten.')
    if 'clips' in raw:
        raise PipelineError('not_scaffold', 'source', 'This timeline already has clips.')
    from .media import probe, stream_duration
    original = (source.parent / raw['source']).resolve()
    info = probe(original)
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    if video is None:
        raise PipelineError('missing_video', 'source', 'Scaffold source has no video stream.')
    fps = rate(raw.get('video', {}).get('fps', 30))
    available = stream_duration(video, info)
    if available is None:
        raise PipelineError('unknown_duration', 'source', 'Cannot derive a full-source cut.')
    cuts = raw.get('cuts', [])
    if cuts:
        raise PipelineError('scaffold_cuts', 'cuts', 'Nonempty legacy cuts have no defined schema.', 'Translate these editorial notes explicitly into clips rather than discarding them.')
    import os
    spec = {'version': 1, 'revision': 0, 'video': raw.get('video', {}),
        'clips': [{'source': os.path.relpath(original, destination.parent), 'duration': float(int(available * float(fps)) / fps), 'audio': {'mode': 'preserve'}}],
        'output': os.path.relpath((source.parent / raw.get('output', '../output/final.mp4')).resolve(), destination.parent)}
    timeline = normalize(spec, destination.parent, path=destination, media=True)
    with FileLock(destination.with_name('.' + destination.name + '.edit.lock')):
        if destination.exists():
            raise PipelineError('destination_exists', 'destination', 'Another editor created the destination.')
        write_json(destination, timeline.spec)
    return timeline.spec
