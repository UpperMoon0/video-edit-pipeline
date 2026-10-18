"""Bounded FFmpeg execution with responsive cancellation of the owned child."""
from __future__ import annotations
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
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
    # Only the child created here is controlled. No unrelated PID is signalled.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            child = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL)
        except OSError as exc:
            raise PipelineError('process_start', command[0], str(exc)) from exc
        try:
            deadline = time.monotonic() + timeout
            while child.poll() is None:
                check_cancel(cancel)
                if time.monotonic() >= deadline:
                    raise PipelineError('process_timeout', command[0], 'The media operation exceeded its time limit.')
                time.sleep(.1)
        except BaseException:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            raise
        def read(stream):
            stream.seek(0, 2)
            if stream.tell() > 16 * 1024 * 1024:
                raise PipelineError('process_output_budget', command[0], 'Process diagnostics exceeded 16 MiB; output is not silently truncated.')
            stream.seek(0)
            return stream.read().decode('utf-8', errors='replace')
        out, err = read(stdout), read(stderr)
        if child.returncode:
            raise PipelineError('process_failed', command[0], err[-12000:], f'Exit {child.returncode}; prior output was preserved.')
        check_cancel(cancel)
        return subprocess.CompletedProcess(command, child.returncode, out, err)


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
