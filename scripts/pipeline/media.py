"""FFmpeg execution and probing; cancellation is cooperative between stages."""
from __future__ import annotations
import json
import math
import os
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from .common import PipelineError


class Cancelled(PipelineError):
    def __init__(self):
        super().__init__('cancelled', 'operation', 'Cancelled; previous deliverables were preserved.', 'Retry to reuse completed work.')


def check_cancel(cancel):
    if cancel and cancel():
        raise Cancelled()


def tool(name):
    value = os.environ.get('PIPELINE_' + name.upper(), name)
    result = shutil.which(value)
    if not result:
        raise PipelineError('missing_tool', name, f'Executable not found: {value}', f'Install {name} or set PIPELINE_{name.upper()}.')
    return str(Path(result).resolve())


def windows_command_units(command):
    return len(subprocess.list2cmdline(command).encode('utf-16-le')) // 2 + 1


def check_command(command):
    units = windows_command_units(command)
    if units > 32000:
        raise PipelineError('command_budget', 'assets', f'Command requires {units} UTF-16 units (budget 32000).',
            'Use shorter paths or precompose excessive simultaneous tracks; video cuts are already chunked.')


def run(command, *, cwd=None, cancel=None, timeout=1800):
    check_command(command)
    check_cancel(cancel)
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
            encoding='utf-8', errors='replace', check=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.CalledProcessError as exc:
        raise PipelineError('process_failed', command[0], exc.stderr[-12000:], f'Exit {exc.returncode}; prior outputs were preserved.') from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PipelineError('process_error', command[0], str(exc), 'Run doctor and check paths/time limits.') from exc
    check_cancel(cancel)
    return result


def ffmpeg_args():
    return [tool('ffmpeg'), '-hide_banner', '-nostdin', '-loglevel', 'error', '-y',
            '-threads', '1', '-filter_threads', '1', '-filter_complex_threads', '1']


def probe(path, count_frames=False):
    command = [tool('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json']
    if count_frames:
        command += ['-count_frames']
    info = json.loads(run(command + [str(path)]).stdout)
    if not info.get('streams'):
        raise PipelineError('missing_stream', str(path), 'No media streams found.')
    return info


def stream_duration(stream, info=None):
    try:
        if 'duration' in stream:
            value = float(stream['duration'])
        elif stream.get('duration_ts') is not None:
            value = float(Fraction(stream['time_base']) * int(stream['duration_ts']))
        elif stream.get('tags', {}).get('DURATION'):
            h, m, s = stream['tags']['DURATION'].split(':')
            value = int(h) * 3600 + int(m) * 60 + float(s) - float(stream.get('start_time', 0))
        elif info and 'duration' in info.get('format', {}):
            value = float(info['format']['duration']) - max(0, float(stream.get('start_time', 0)))
        else:
            return None
        return value if value > 0 and math.isfinite(value) else None
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        return None
