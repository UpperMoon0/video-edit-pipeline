"""Render orchestration: owned temporary work, lossless chunks, and QA publication."""
import shutil
import tempfile
import uuid
from pathlib import Path
from .common import (PipelineError, FileLock, file_hash, read_json, write_json,
    atomic_write, output_transaction, reject_alias, utcnow)
from .media import run, tool, ffmpeg_args, check_command, check_cancel
from .timeline import preflight
from .render_chunks import prepare_chunk, prune_cache, clip_command
from .render_video import add_video
from .render_audio import add_audio
from .qa import inspect_output, require_pass
from .captions import retime, as_srt


def final_command(timeline, work, output):
    command = ffmpeg_args() + ['-f', 'concat', '-safe', '0', '-i', str(work / 'cuts.ffconcat')]
    filters = []
    video, index = add_video(timeline, command, filters, work)
    index = add_audio(timeline, command, filters, index)
    captions = timeline.spec.get('captions', {})
    subtitle_index = None
    if captions.get('mode') == 'burn':
        raise PipelineError('unsupported_burn', 'captions.mode', 'Burn-in is not available in this revision; use sidecar or mux.')
    if captions.get('mode') == 'mux':
        command += ['-i', str(work / 'captions.srt')]
        subtitle_index = index
    command += ['-filter_complex_script', str(work / 'final.ffgraph'), '-map', f'[{video}]', '-map', '[outa]']
    if subtitle_index is not None:
        command += ['-map', f'{subtitle_index}:s:0', '-c:s', 'srt' if timeline.output.suffix == '.mkv' else 'mov_text']
    encode = timeline.spec.get('encode', {})
    command += ['-c:v', 'libx264', '-preset', encode.get('preset', 'medium'), '-crf', str(encode.get('crf', 18)),
        '-threads', '1', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-r', str(timeline.fps), '-t', f'{timeline.duration:.9f}']
    if timeline.output.suffix.lower() in ('.mp4', '.mov'):
        command += ['-movflags', '+faststart']
    command += [str(output)]
    check_command(command)
    return command, ';\n'.join(filters)


def command_plan(timeline):
    preflight(timeline)
    work = timeline.output.parent / '.render-work-PREVIEW'
    commands, graphs = [], []
    for i, (clip, frames) in enumerate(zip(timeline.spec['clips'], timeline.frames)):
        command, graph = clip_command(timeline, clip, frames, work / f'cut-{i}.mkv', work / f'cut-{i}.ffgraph')
        commands.append(command)
        graphs.append(graph)
    command, graph = final_command(timeline, work, timeline.output)
    return {'version': 1, 'mode': 'command-inspection', 'duration': timeline.duration, 'frames': sum(timeline.frames),
        'commands': commands + [command], 'filter_graphs': graphs + [graph], 'writes_performed': False}


def render(timeline, *, cache_enabled=True, cache_bytes=1073741824, overwrite=True, cancel=None):
    preflight(timeline)
    check_cancel(cancel)
    assets = timeline.assets() + ([timeline.path] if timeline.path else [])
    identities = {str(p): file_hash(p) for p in assets}
    version = run([tool('ffmpeg'), '-version']).stdout.splitlines()[0]
    hits = 0
    output = timeline.output
    with output_transaction(output, assets, overwrite) as temp:
        with tempfile.TemporaryDirectory(prefix='.render-work-', dir=output.parent) as directory:
            work = Path(directory)
            cache = output.parent / '.pipeline-cache' if cache_enabled else work / 'cache'
            if any(p.is_relative_to(cache) for p in assets):
                raise PipelineError('cache_input', 'source', 'Inputs cannot be stored in the managed render cache.')
            with FileLock(cache.with_name(cache.name + '.lock')):
                marker = cache / 'owner.json'
                if cache.exists() and not marker.exists() and any(cache.iterdir()):
                    raise PipelineError('unowned_cache', str(cache), 'Refusing to reuse an unowned nonempty cache.')
                cache.mkdir(parents=True, exist_ok=True)
                if marker.exists() and read_json(marker) != {'pipeline_cache': 1}:
                    raise PipelineError('cache_version', str(cache), 'Unrecognized cache marker.')
                write_json(marker, {'pipeline_cache': 1})
                lines = ['ffconcat version 1.0']
                for i, (clip, frames) in enumerate(zip(timeline.spec['clips'], timeline.frames)):
                    check_cancel(cancel)
                    chunk, hit = prepare_chunk(timeline, clip, frames, cache, work, identities, version, cancel)
                    hits += int(hit)
                    local = work / f'cut-{i:05d}.mkv'
                    try:
                        local.hardlink_to(chunk)
                    except OSError:
                        shutil.copyfile(chunk, local)
                    lines += [f"file '{local.name}'", f'duration {clip["duration"]:.9f}']
                    prune_cache(cache, cache_bytes)
                (work / 'cuts.ffconcat').write_text('\n'.join(lines) + '\n', encoding='utf-8')
                captions = None
                if timeline.spec.get('captions'):
                    cues = retime(timeline)
                    if not cues and timeline.spec['captions'].get('mode') == 'mux':
                        raise PipelineError('empty_captions', 'captions', 'No selected audible transcript cues.')
                    captions = as_srt(cues)
                    (work / 'captions.srt').write_text(captions, encoding='utf-8')
                command, graph = final_command(timeline, work, temp)
                (work / 'final.ffgraph').write_text(graph, encoding='utf-8')
                run(command, cwd=work, cancel=cancel)
                report = inspect_output(temp, timeline.fps, sum(timeline.frames), qa=timeline.spec.get('qa'),
                    loudness=timeline.spec['audio'].get('loudness'), cancel=cancel)
                report.update(timeline_revision=timeline.spec['revision'], timeline=timeline.spec, sources=identities,
                    ffmpeg=version, created_at=utcnow(), cache_hits=hits, output=str(output))
                if any(file_hash(Path(p)) != sha for p, sha in identities.items()):
                    report['passed'] = False
                    report['errors'].append('An input changed during rendering.')
                report_dir = output.parent / '.pipeline-reports'
                report_path = report_dir / (uuid.uuid4().hex + '.json')
                if captions is not None:
                    sidecar = report_path.with_suffix('.srt')
                    atomic_write(sidecar, captions.encode('utf-8'))
                    report['captions_sidecar'] = str(sidecar)
                write_json(report_path, report)
                require_pass(report)
                check_cancel(cancel)
    return {'version': 1, 'status': 'complete', 'output': str(output), 'qa_report': str(report_path),
        'sha256': report['output_sha256'], 'duration': timeline.duration, 'frames': sum(timeline.frames), 'cache_hits': hits}
