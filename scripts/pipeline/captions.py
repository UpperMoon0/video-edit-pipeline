"""Cut-aware captions derived from audible transcript evidence."""
from .common import read_json


def timestamp(seconds):
    ms = max(0, round(seconds * 1000))
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}'


def selected_cues(transcript, start, end, offset):
    result = []
    for segment in transcript.get('segments', []):
        a, b = segment['start'], segment['end']
        words = segment.get('words') or []
        if words:
            words = [w for w in words if start <= w['start'] < w['end'] <= end]
            if not words:
                continue
            a, b = words[0]['start'], words[-1]['end']
            text = ''.join(w['text'] for w in words)
        elif start <= a < b <= end:
            text = segment['text']
        else:
            continue
        result.append(dict(start=a-start+offset, end=b-start+offset, text=text.strip()))
    return result


def retime(timeline):
    audio = timeline.spec['audio']
    captions = timeline.spec.get('captions', {})
    if captions.get('kind') == 'narration':
        start = audio.get('voiceover_source_in', 0)
        offset = audio.get('voiceover_start', 0)
        return selected_cues(read_json(timeline.asset(captions['transcript'])), start, start+timeline.duration-offset, offset)
    result, offset = [], 0
    for clip in timeline.spec['clips']:
        info = timeline.media.get(str(timeline.asset(clip['source'])), {})
        audible = any(s['codec_type'] == 'audio' for s in info.get('streams', []))
        if audible and clip['audio']['mode'] == 'preserve' and clip['audio'].get('gain', 1) > 0 and clip.get('transcript'):
            result += selected_cues(read_json(timeline.asset(clip['transcript'])), clip['in'], clip['in']+clip['duration'], offset)
        offset += clip['duration']
    return result


def as_srt(cues):
    return '\n'.join(f'{i}\n{timestamp(c["start"])} --> {timestamp(c["end"])}\n{c["text"]}\n' for i, c in enumerate(cues, 1))
