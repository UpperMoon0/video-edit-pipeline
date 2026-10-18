#!/usr/bin/env python3
"""Generate synthetic public examples, never download or inspect personal media."""
import argparse
import json
import os
import subprocess
from pathlib import Path


def generate(root):
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError('Fixture generation requires a new or empty directory; existing files are never overwritten.')
    root.mkdir(parents=True, exist_ok=True)
    common = [os.environ.get('PIPELINE_FFMPEG', 'ffmpeg'), '-hide_banner', '-loglevel', 'error', '-y', '-threads', '1', '-filter_threads', '1']
    for color, frequency in [('red', 440), ('green', 880)]:
        subprocess.run(common + ['-f', 'lavfi', '-i', f'color=c={color}:s=160x96:r=30:d=3',
            '-f', 'lavfi', '-i', f'sine=frequency={frequency}:sample_rate=48000:duration=3',
            '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', '-c:a', 'pcm_s16le', str(root / f'{color}.mkv')], check=True)
    for name, frequency, duration in [('voice', 660, 1), ('music', 220, 4), ('effect', 1500, .3)]:
        subprocess.run(common + ['-f', 'lavfi', '-i', f'sine=frequency={frequency}:sample_rate=48000:duration={duration}',
            '-c:a', 'pcm_s16le', str(root / f'{name}.wav')], check=True)
    (root / 'overlay.ppm').write_bytes(b'P6\n32 16\n255\n' + bytes([255, 255, 255]) * 32 * 16)
    minimal = {'version': 1, 'video': {'width': 160, 'height': 96, 'fps': 30},
        'clips': [{'id': 'red', 'source': 'red.mkv', 'duration': 2}, {'id': 'green', 'source': 'green.mkv', 'duration': 2}],
        'audio': {'voiceover': 'voice.wav', 'music': [{'source': 'music.wav', 'start': 0, 'end': 4, 'volume': .4, 'fade_in': 0, 'fade_out': 0}]},
        'encode': {'preset': 'ultrafast'}, 'output': 'output/minimal.mp4'}
    (root / 'minimal.json').write_text(json.dumps(minimal, indent=2), encoding='utf-8')
    rich = json.loads(json.dumps(minimal))
    rich['output'] = 'output/rich.mp4'
    for clip in rich['clips']:
        clip['audio'] = {'mode': 'preserve', 'gain': .3}
    rich['overlays'] = [{'source': 'overlay.ppm', 'start': 1, 'duration': 2, 'width': 64, 'fade_in': .2, 'fade_out': .2}]
    rich['audio']['sfx'] = [{'source': 'effect.wav', 'start': 3, 'duration': .3, 'volume': .5}]
    (root / 'rich.json').write_text(json.dumps(rich, indent=2), encoding='utf-8')
    return root


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    generate(parser.parse_args().output)
