"""Bounded per-cut rendering; cached intermediates contain no global effects."""
from pathlib import Path
from fractions import Fraction
from .common import file_hash, digest, read_json, write_json, output_transaction, PipelineError
from .media import ffmpeg_args, run, check_command, check_cancel
from .qa import inspect_output, require_pass
from .timeline import frame_count


def clip_command(timeline, clip, frames, destination, graph_path, source=None):
    duration = clip['duration']
    width, height = timeline.spec['video']['width'], timeline.spec['video']['height']
    zoom = clip.get('zoom', 1)
    sw, sh = round(width * zoom / 2) * 2, round(height * zoom / 2) * 2
    command = ffmpeg_args()
    if clip['type'] == 'image':
        command += ['-loop', '1', '-framerate', str(timeline.fps)]
    command += ['-i', str(source or timeline.asset(clip['source']))]
    info = timeline.media[str(timeline.asset(clip['source']))]
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    origin = float(info.get('format', {}).get('start_time', 0))
    first = max(0, float(video.get('start_time', origin)) - origin)
    start_frame = frame_count(max(0, Fraction(str(clip['in'])) - Fraction(str(first))), timeline.fps)
    # Resample before trimming, retaining neighboring frames and one stable
    # source-time phase across splits, trims, and range previews.
    filters = [f'[0:v:0]setpts=PTS-STARTPTS,scale={sw}:{sh}:force_original_aspect_ratio=increase,'
        f'crop={width}:{height},setsar=1,fps={timeline.fps}:start_time=0:round=near,'
        f'trim=start_frame={start_frame}:end_frame={start_frame + frames},setpts=N/({timeline.fps}*TB),format=yuv420p[v]']
    samples = round(duration * 48000)
    policy = clip['audio']
    has_audio = any(s['codec_type'] == 'audio' for s in timeline.media[str(timeline.asset(clip['source']))]['streams'])
    if policy['mode'] == 'preserve' and has_audio and clip['type'] == 'video':
        filters.append(f'[0:a:{policy.get("stream", 0)}]aresample=48000:async=1:first_pts=0,'
            f'aformat=sample_fmts=fltp:channel_layouts=stereo,volume={policy.get("gain", 1)},'
            f'apad,atrim=start_sample={round(clip["in"] * 48000)}:'
            f'end_sample={round(clip["in"] * 48000) + samples},asetpts=N/SR/TB[a]')
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
    implementation = digest({name: file_hash(Path(__file__).with_name(name)) for name in ('render_chunks.py', 'qa.py', 'media.py', 'timeline.py')})
    source = timeline.asset(clip['source'])
    expected = identities[str(source)]
    key = digest({'format': 3, 'implementation': implementation, 'source': expected,
        'cut': properties, 'video': timeline.spec['video'], 'ffmpeg': version})
    output, receipt = cache / (key + '.mkv'), cache / (key + '.json')
    if output.is_file() and receipt.is_file():
        try:
            record = read_json(receipt)
        except PipelineError:
            record = {}  # An incomplete owned receipt is a cache miss, not a deliverable.
        if (isinstance(record, dict) and record.get('source_sha256') == expected
                and record.get('output_sha256') == file_hash(output, cancel) and record.get('passed')):
            output.touch()
            return output, True
    graph_path = work / (key + '.ffgraph')
    # FFmpeg must never read mutable caller media for a persistent cache miss.
    # Copy once per source/render into our private workspace and verify the
    # bytes, not just metadata. A replacement of the original during encoding
    # cannot bind different footage to the earlier source identity.
    snapshot = work / ('source-' + expected + source.suffix)
    if not snapshot.exists():
        with source.open('rb') as original, snapshot.open('xb') as target:
            while block := original.read(4 * 1024 * 1024):
                check_cancel(cancel)
                target.write(block)
    if file_hash(snapshot, cancel) != expected:
        raise PipelineError('source_changed', str(source), 'Source changed before cache construction.')
    with output_transaction(output, timeline.assets()) as temp:
        command, graph = clip_command(timeline, clip, frames, temp, graph_path, source=snapshot)
        graph_path.write_text(graph, encoding='utf-8')
        run(command, cancel=cancel)
        report = inspect_output(temp, timeline.fps, frames, cancel=cancel)
        require_pass(report)
        if file_hash(snapshot, cancel) != expected or file_hash(source, cancel) != expected:
            raise PipelineError('source_changed', str(source), 'Source changed during cache construction.')
        report['source_sha256'] = expected
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
