"""Global image/title composition after exact cut concatenation."""
from .titles import coordinate, add_titles


def add_video(timeline, command, filters, work, write=False):
    fps, total = str(timeline.fps), timeline.duration
    filters.append(f'[0:v:0]setpts=N/({fps}*TB)[basev]')
    current, index = 'basev', 1
    for number, overlay in enumerate(timeline.spec.get('overlays', [])):
        start, duration = overlay['start'], overlay['duration']
        original = overlay.get('_original_duration', duration)
        phase = overlay.get('_fade_phase', 0)
        fade_in = overlay.get('fade_in', min(.5, original / 2))
        fade_out = overlay.get('fade_out', min(.5, original / 2))
        command += ['-loop', '1', '-framerate', fps, '-t', f'{total:.9f}', '-i', str(timeline.asset(overlay['source']))]
        label, output = f'overlay{number}', f'withoverlay{number}'
        width = overlay.get('width', min(800, timeline.spec['video']['width']))
        chain = f'[{index}:v:0]fps={fps},scale={width}:-1,format=rgba,colorchannelmixer=aa={overlay.get("opacity", 1)},setpts=PTS-STARTPTS+{phase:.9f}/TB'
        if fade_in:
            chain += f',fade=t=in:st={start:.9f}:d={fade_in:.9f}:alpha=1'
        if fade_out:
            chain += f',fade=t=out:st={start + original - fade_out:.9f}:d={fade_out:.9f}:alpha=1'
        filters.append(chain + f',setpts=PTS-STARTPTS[{label}]')
        x, y = coordinate(overlay.get('x'), 'x'), coordinate(overlay.get('y'), 'y')
        filters.append(f'[{current}][{label}]overlay=x={x}:y={y}:eof_action=pass:'
            f"enable='gte(t,{start:.9f})*lt(t,{start + duration:.9f})'[{output}]")
        current, index = output, index + 1
    return add_titles(timeline, current, filters, work, write=write), index
