"""Precise source-time sampling with fresh-frame evidence and owned-run cleanup."""
import math
import re
import shutil
import uuid
from fractions import Fraction
from pathlib import Path
from .common import FileLock, PipelineError, read_json, write_json, file_hash
from .media import probe, stream_duration, run, ffmpeg_args, check_cancel


def sample_video(source, output, *, interval=10, start=0, end=0, columns=4, rows=4, width=320, count=None, cancel=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    for field, value in [('interval', interval), ('start', start), ('end', end)]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (field == 'interval' and value == 0):
            raise PipelineError('sample_parameter', field, 'Sampling times must be finite; interval must be positive.')
    for field, value in [('columns', columns), ('rows', rows), ('width', width)]:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= (4096 if field == 'width' else 64):
            raise PipelineError('sample_parameter', field, 'Layout and thumbnail dimensions must be positive, bounded integers.')
    if count is not None and (isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 4096):
        raise PipelineError('sample_parameter', 'count', 'Use 1..4096 samples.')
    info = probe(source)
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    if not video:
        raise PipelineError('missing_video', str(source), 'This asset has no video frames to sample.')
    duration = stream_duration(video, info)
    if duration is None:
        raise PipelineError('unknown_duration', str(source), 'Video duration is unavailable.')
    stop = duration if end == 0 else end
    if not start < stop <= duration + 1e-6:
        raise PipelineError('sample_range', 'start/end', 'Require 0 <= start < end <= video duration.')
    try:
        frame_step = 1 / float(Fraction(video.get('avg_frame_rate', '30/1')))
    except (ValueError, ZeroDivisionError):
        frame_step = 1 / 30
    frame_step = max(.001, min(frame_step, .5))
    total = count if count is not None else math.ceil((stop - start) / interval)
    if total > 4096:
        raise PipelineError('sample_budget', 'interval', 'Requested more than 4096 samples.', 'Increase interval or narrow the range.')
    if source.is_relative_to(output):
        raise PipelineError('sampling_input_directory', 'output', 'Keep sampling output separate from the source directory.')
    with FileLock(output.with_name('.' + output.name + '.samples.lock')):
        output.mkdir(parents=True, exist_ok=True)
        index_path = output / 'index.json'
        previous = read_json(index_path) if index_path.exists() else None
        run_dir = output / ('sample-run-' + uuid.uuid4().hex)
        run_dir.mkdir()
        write_json(run_dir / 'owner.json', {'pipeline_samples': 1})
        frames, published = [], False
        try:
            for i in range(total):
                check_cancel(cancel)
                target = start + (i + .5) * ((stop - start) / total if count else interval)
                target = min(target, max(start, stop - frame_step))
                frame = run_dir / f'frame-{i:04d}.jpg'
                success = None
                for attempt in range(16):
                    seek = max(start, target - attempt * frame_step)
                    frame.unlink(missing_ok=True)
                    result = run(ffmpeg_args() + ['-loglevel', 'info', '-ss', f'{seek:.9f}', '-i', str(source),
                        '-frames:v', '1', '-vf', f'scale={width}:-2,showinfo', '-q:v', '3', str(frame)], cancel=cancel)
                    stamps = re.findall(r'\bpts_time:([-+0-9.eE]+)', result.stderr)
                    actual = seek + float(stamps[0]) if stamps else None
                    if frame.is_file() and frame.stat().st_size > 0 and actual is not None and start - 1e-6 <= actual < stop - 1e-7:
                        success = {'index': i, 'timestamp': actual, 'seek': seek, 'fallback_attempts': attempt,
                            'frame': str(frame.relative_to(output)), 'sheet': i // (columns * rows) + 1}
                        break
                    if seek == start:
                        break
                if success is None:
                    raise PipelineError('empty_frame', f'samples.{i}', 'No usable frame was decoded inside the requested range.', 'Widen the range or remux damaged media.')
                frames.append(success)
            sheets = []
            per_sheet = columns * rows
            for i in range(math.ceil(total / per_sheet)):
                amount = min(per_sheet, total - i * per_sheet)
                sheet = run_dir / f'sheet-{i+1:02d}.jpg'
                run(ffmpeg_args() + ['-framerate', '1', '-start_number', str(i * per_sheet), '-i', str(run_dir / 'frame-%04d.jpg'),
                    '-vf', f'tile={columns}x{rows}:nb_frames={amount}:padding=2:margin=2:color=black', '-frames:v', '1', str(sheet)], cancel=cancel)
                if not sheet.is_file() or not sheet.stat().st_size:
                    raise PipelineError('empty_sheet', 'sampling', 'Contact sheet was not produced.')
                sheets.append(str(sheet.relative_to(output)))
            result = {'version': 2, 'analysis_version': 1, 'input': str(source), 'source_sha256': file_hash(source),
                'duration': duration, 'start_seconds': start, 'end_seconds': stop, 'interval_seconds': interval,
                'frame_count': total, 'columns': columns, 'rows': rows, 'thumbnail_width': width,
                'run': run_dir.name, 'frames': frames, 'sheets': sheets}
            check_cancel(cancel)
            write_json(index_path, result)
            published = True
            if previous and previous.get('version') == 2:
                old_name = previous.get('run', '')
                if re.fullmatch(r'sample-run-[0-9a-f]{32}', old_name) and old_name != run_dir.name:
                    old = output / old_name
                    if old.is_dir() and (old / 'owner.json').is_file() and read_json(old / 'owner.json') == {'pipeline_samples': 1}:
                        shutil.rmtree(old)
            return result
        finally:
            if not published:
                shutil.rmtree(run_dir)
