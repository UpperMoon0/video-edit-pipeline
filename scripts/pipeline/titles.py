"""Typed titles use data files and disabled expansion, not user filter expressions."""
import os
import shutil
import textwrap
from pathlib import Path
from .common import PipelineError


def coordinate(value, axis, text=False):
    w, item = (('w', 'text_w') if axis == 'x' else ('h', 'text_h')) if text else (('main_w', 'overlay_w') if axis == 'x' else ('main_h', 'overlay_h'))
    if isinstance(value, (int, float)):
        return str(value)
    if value in ('left', 'top'):
        return '0'
    if value in ('right', 'bottom'):
        return w + '-' + item
    return '(' + w + '-' + item + ')/2'


def default_font():
    candidates = [os.environ.get('PIPELINE_FONT'),
        str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'arial.ttf'),
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf']
    for path in candidates:
        if path and Path(path).is_file():
            return Path(path)
    raise PipelineError('missing_font', 'titles.font', 'No local fallback font was found.', 'Specify titles[].font or PIPELINE_FONT.')


def add_titles(timeline, current, filters, work, write=False):
    for number, title in enumerate(timeline.spec.get('titles', [])):
        font = timeline.asset(title['font']) if title.get('font') else default_font()
        font_name = 'font-' + str(number) + '.ttf'
        text_name = 'title-' + str(number) + '.txt'
        size = title.get('size', 48)
        if write:
            shutil.copyfile(font, work / font_name)
            columns = max(4, int(timeline.spec['video']['width'] / (size * 0.65)))
            lines = [textwrap.fill(line, columns) for line in title['text'].splitlines()]
            (work / text_name).write_text('\n'.join(lines), encoding='utf-8')
        x = coordinate(title.get('x'), 'x', True)
        y = coordinate(title.get('y'), 'y', True)
        box = int(title.get('box', title.get('type') == 'callout'))
        start, stop = title['start'], title['start'] + title['duration']
        output = 'title' + str(number)
        chain = f'[{current}]drawtext=fontfile={font_name}:textfile={text_name}:expansion=none'
        chain += f':fontsize={size}:fontcolor={title.get("color", "white")}:x={x}:y={y}:box={box}:boxcolor=black@0.65'
        chain += f":enable='gte(t,{start:.9f})*lt(t,{stop:.9f})'[{output}]"
        filters.append(chain)
        current = output
    return current
