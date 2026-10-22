"""Create an original synthetic karaoke fixture outside the public checkout."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from pipeline.common import PipelineError, write_json
from pipeline.media import ffmpeg_args, run


def generate(destination):
    destination = Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise PipelineError('example_exists', 'destination', 'Use a new or empty directory for synthetic fixtures.')
    destination.mkdir(parents=True, exist_ok=True)
    source = destination / 'synthetic.mp4'
    run(ffmpeg_args() + ['-f', 'lavfi', '-i', 'color=c=0x80b6a0:s=640x360:r=30:d=4',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100:duration=4',
        '-c:v', 'libx264', '-threads', '1', '-c:a', 'aac', '-shortest', str(source)])
    run(ffmpeg_args() + ['-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=44100:duration=4',
                        str(destination / 'replacement.wav')])
    spec = {'version': 1, 'title': 'Synthetic sing-along', 'source': 'synthetic.mp4', 'language': 'en',
        'intro': 'An original synthetic production fixture.', 'credits': [],
        'cues': [
            {'start': .5, 'end': 1.5, 'text': 'Light and sound', 'translation': 'Light and sound',
             'syllables': [{'text': 'Light', 'start': .5, 'end': .8}, {'text': 'and', 'start': .8, 'end': 1.1},
                           {'text': 'sound', 'start': 1.1, 'end': 1.5}]},
            {'start': 3, 'end': 3.8, 'text': 'Sing with me', 'translation': 'Sing with me',
             'syllables': [{'text': 'Sing', 'start': 3, 'end': 3.3}, {'text': 'with', 'start': 3.3, 'end': 3.5},
                           {'text': 'me', 'start': 3.5, 'end': 3.8}]}]}
    write_json(destination / 'karaoke.json', spec)
    return destination


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    print(generate(parser.parse_args().destination))
