"""First-pass measurement of the exact assembled audio, before delivery encoding."""
import json
import math
import re
from .common import PipelineError
from .media import ffmpeg_args, run, check_command
from .render_audio import add_audio


def analysis_plan(timeline, work):
    command = ffmpeg_args() + ['-loglevel', 'info', '-f', 'concat', '-safe', '0', '-i', str(work / 'cuts.ffconcat')]
    filters = []
    add_audio(timeline, command, filters, 1, normalization=False)
    target = timeline.spec['audio']['loudness']
    filters.append(f'[outa]loudnorm=I={target["integrated"]}:TP={target["true_peak"]}:LRA={target.get("range", 11)}:print_format=json[measured]')
    command += ['-filter_complex_script', str(work / 'loudness-analysis.ffgraph'), '-map', '[measured]', '-f', 'null', '-']
    check_command(command)
    return command, ';\n'.join(filters)


def measure_audio(timeline, work, cancel=None):
    command, graph = analysis_plan(timeline, work)
    (work / 'loudness-analysis.ffgraph').write_text(graph, encoding='utf-8')
    result = run(command, cwd=work, cancel=cancel)
    candidates = re.findall(r'\{[^{}]*"input_i"[^{}]*\}', result.stderr, re.S)
    if not candidates:
        raise PipelineError('loudness_measurement', 'audio.loudness', 'FFmpeg did not return first-pass loudness measurements.')
    raw = json.loads(candidates[-1])
    mapping = {'measured_I': 'input_i', 'measured_LRA': 'input_lra', 'measured_TP': 'input_tp',
               'measured_thresh': 'input_thresh', 'offset': 'target_offset'}
    measurements = {key: float(raw[field]) for key, field in mapping.items()}
    if any(not math.isfinite(value) for value in measurements.values()):
        raise PipelineError('unmeasurable_loudness', 'audio.loudness', 'Audio is silent or too short for finite loudness measurements.',
                            'Disable the loudness target for intentional silence, or provide a measurable program.')
    return measurements
