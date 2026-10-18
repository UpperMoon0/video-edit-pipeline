"""Decoded stream invariants and opt-in perceptual QA gates."""
from __future__ import annotations
import json
import math
import re
from fractions import Fraction
from .common import PipelineError, file_hash
from .media import probe, run, ffmpeg_args, stream_duration


def inspect_output(path, fps, frames, *, qa=None, loudness=None, cancel=None):
    qa = qa or {}
    info = probe(path, count_frames=True)
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
    errors, metrics = [], {}
    expected = float(Fraction(frames, 1) / fps)
    if not video or not audio:
        errors.append('Expected both video and audio streams.')
    else:
        actual_frames = int(video.get('nb_read_frames', 0))
        actual_fps = Fraction(video.get('avg_frame_rate', '0/1'))
        vd, ad = stream_duration(video, info), stream_duration(audio, info)
        metrics.update(video_frames=actual_frames, fps=str(actual_fps), video_duration=vd, audio_duration=ad)
        if actual_frames != frames:
            errors.append(f'Video has {actual_frames} frames, expected {frames}.')
        if actual_fps != fps:
            errors.append(f'Video rate {actual_fps} differs from expected {fps}.')
        if vd is None or abs(vd - expected) > float(1 / fps) + .002:
            errors.append('Video duration differs from frame-grid duration.')
        if ad is None or abs(ad - expected) > qa.get('audio_tolerance_seconds', .06):
            errors.append('Audio does not cover timeline duration within codec tolerance.')
    run(ffmpeg_args() + ['-xerror', '-i', str(path), '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'], cancel=cancel)
    if loudness or 'max_true_peak_db' in qa:
        result = run(ffmpeg_args() + ['-loglevel', 'info', '-i', str(path), '-vn', '-af',
            'loudnorm=I=-16:TP=-1:LRA=11:print_format=json', '-f', 'null', '-'], cancel=cancel)
        matches = re.findall(r'\{[^{}]*"input_i"[^{}]*\}', result.stderr, re.S)
        if not matches:
            errors.append('Loudness measurement unavailable.')
        else:
            measured = json.loads(matches[-1])
            def metric(name):
                value = float(measured[name])
                return value if math.isfinite(value) else None
            metrics.update(integrated_lufs=metric('input_i'), true_peak_db=metric('input_tp'))
            peak_limit = qa.get('max_true_peak_db', loudness.get('true_peak', 0) + .3 if loudness else 0)
            if metrics['true_peak_db'] is not None and metrics['true_peak_db'] > peak_limit:
                errors.append('True peak exceeds configured limit.')
            if loudness and (metrics['integrated_lufs'] is None or abs(metrics['integrated_lufs'] - loudness['integrated']) > qa.get('loudness_tolerance_lu', 2)):
                errors.append('Integrated loudness is outside configured target tolerance.')
    for kind, key in [('silence', 'max_silence_seconds'), ('black', 'max_black_seconds')]:
        if key in qa:
            filter_arg = ['-af', 'silencedetect=noise=-50dB:d=0.05'] if kind == 'silence' else ['-vf', 'blackdetect=d=0.05:pix_th=0.1']
            result = run(ffmpeg_args() + ['-loglevel', 'info', '-i', str(path)] + filter_arg + ['-f', 'null', '-'], cancel=cancel)
            durations = [float(v) for v in re.findall(kind + r'_duration[: ]+([0-9.]+)', result.stderr)]
            metrics['max_' + kind + '_seconds'] = max(durations, default=0)
            if metrics['max_' + kind + '_seconds'] > qa[key]:
                errors.append(f'{kind} duration exceeds configured maximum.')
    return {'version': 1, 'passed': not errors, 'expected_frames': frames, 'expected_duration': expected,
            'metrics': metrics, 'errors': errors, 'output_sha256': file_hash(path), 'decoded': True}


def require_pass(report):
    if not report['passed']:
        raise PipelineError('qa_failed', 'output', '; '.join(report['errors']), 'Previous deliverable preserved; inspect the QA report.')
