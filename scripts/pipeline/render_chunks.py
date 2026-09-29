"""Bounded per-cut rendering; cached intermediates contain no global effects."""
from pathlib import Path
from .common import digest, read_json, write_json, output_transaction, PipelineError
from .media import ffmpeg_args, run, check_command
from .qa import inspect_output, require_pass


def clip_command(timeline, clip, frames, destination, graph_path):
    duration = clip['duration']
    width, height = timeline.spec['video']['width'], timeline.spec['video']['height']
    zoom = clip.get('zoom', 1)
    sw, sh = round(width * zoom / 2) * 2, round(height * zoom / 2) * 2
    command = ffmpeg_args()
    if clip['type'] == 'image':
        command += ['-loop', '1', '-framerate', str(timeline.fps)]
    else:
        command += ['-ss', f'{clip["in"]:.9f}']
    command += ['-i', str(timeline.asset(clip['source']))]
    filters = [f'[0:v:0]setpts=PTS-STARTPTS,scale={sw}:{sh}:force_original_aspect_ratio=increase,'
        f'crop={width}:{height},setsar=1,fps={timeline.fps}:start_time=0:round=near,'
        f'trim=end_frame={frames},setpts=N/({timeline.fps}*TB),format=yuv420p[v]']
    samples = round(duration * 48000)
    policy = clip['audio']
    has_audio = any(s['codec_type'] == 'audio' for s in timeline.media[str(timeline.asset(clip['source']))]['streams'])
    if policy['mode'] == 'preserve' and has_audio and clip['type'] == 'video':
        filters.append(f'[0:a:{policy.get("stream", 0)}]aresample=48000:async=1:first_pts=0,'
            f'aformat=sample_fmts=fltp:channel_layouts=stereo,volume={policy.get("gain", 1)},'
            f'apad,atrim=end_sample={samples},asetpts=N/SR/TB[a]')
    else:
        filters.append(f'anullsrc=r=48000:cl=stereo,atrim=end_sample={samples},asetpts=N/SR/TB[a]')
    command += ['-filter_complex_script', str(graph_path), '-map', '[v]', '-map', '[a]',
        '-c:v', 'ffv1', '-level', '3', '-threads', '1', '-c:a', 'pcm_f32le',
        '-r', str(timeline.fps), '-t', f'{duration:.9f}', str(destination)]
    check_command(command)
    return command, ';\n'.join(filters)


def prepare_chunk(timeline, clip, frames, cache, work, identities, version, cancel=None):
    # IDs, captions, and global audio/graphics do not affect this intermediate.
    properties = {k: clip[k] for k in ('type', 'in', 'duration', 'audio')}
    properties['zoom'] = clip.get('zoom', 1)
    key = digest({'format': 1, 'source': identities[str(timeline.asset(clip['source']))],
        'cut': properties, 'video': timeline.spec['video'], 'ffmpeg': version})
    output, receipt = cache / (key + '.mkv'), cache / (key + '.json')
    if output.is_file() and receipt.is_file():
        from .common import file_hash
        record = read_json(receipt)
        if record.get('output_sha256') == file_hash(output) and record.get('passed'):
            output.touch()
            return output, True
    graph_path = work / (key + '.ffgraph')
    with output_transaction(output, timeline.assets()) as temp:
        command, graph = clip_command(timeline, clip, frames, temp, graph_path)
        graph_path.write_text(graph, encoding='utf-8')
        run(command, cancel=cancel)
        report = inspect_output(temp, timeline.fps, frames, cancel=cancel)
        require_pass(report)
    write_json(receipt, report)
    return output, False


def prune_cache(cache, maximum_bytes):
    """Called under the render cache lock; only hash-named owned files qualify."""
    import re
    files = sorted((p for p in cache.glob('*.mkv') if re.fullmatch(r'[0-9a-f]{64}\.mkv', p.name)), key=lambda p: p.stat().st_mtime)
    size = sum(p.stat().st_size for p in files)
    for path in files:
        if size <= maximum_bytes:
            break
        size -= path.stat().st_size
        path.unlink()
        path.with_suffix('.json').unlink(missing_ok=True)
