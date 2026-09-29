"""Cut-aware captions derived from audible transcript evidence."""
import math
import re
from .common import PipelineError, read_json


def timestamp(seconds):
    ms = max(0, round(seconds * 1000))
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}'


def selected_cues(transcript, start, end, offset):
    if not isinstance(transcript, dict) or not isinstance(transcript.get('segments', []), list):
        raise PipelineError('transcript_schema', 'segments', 'Expected a transcript object with a segment array.')
    if transcript.get('status', 'complete') != 'complete':
        return []
    result = []
    def checked_range(entry, field):
        if not isinstance(entry, dict):
            raise PipelineError('transcript_schema', field, 'Expected a timestamped text object.')
        a, b = entry.get('start'), entry.get('end')
        if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in (a, b)) or not 0 <= a < b:
            raise PipelineError('transcript_range', field, 'Expected finite, positive source-time ranges.')
        if not isinstance(entry.get('text'), str):
            raise PipelineError('transcript_text', field, 'Expected text, not a filter expression or object.')
        return a, b
    for index, segment in enumerate(transcript.get('segments', [])):
        a, b = checked_range(segment, f'segments.{index}')
        words = segment.get('words') or []
        if not isinstance(words, list):
            raise PipelineError('transcript_schema', f'segments.{index}.words', 'Expected a word array.')
        if words:
            selected, previous = [], a
            for word in words:
                lo, hi = checked_range(word, f'segments.{index}.words')
                if lo < previous - .001 or lo < a - .001 or hi > b + .001:
                    raise PipelineError('word_order', f'segments.{index}.words', 'Word ranges must be ordered and contained in their segment.')
                previous = lo
                if start <= lo < hi <= end:
                    selected.append(word)
            if not selected:
                continue
            a, b = selected[0]['start'], selected[-1]['end']
            text = ''.join(w['text'] for w in selected)
        elif start <= a < b <= end:
            text = segment['text']
        else:
            continue
        # Treat transcript content as plain text, never SRT/ASS markup. Collapse
        # blank lines so text cannot terminate a cue and introduce another one.
        text = re.sub(r'\{[^}]*\}|<[^>]*>', '', text)
        text = ' '.join(''.join(c for c in text if ord(c) >= 32 or c in '\n\t').split())
        if text:
            result.append(dict(start=a-start+offset, end=b-start+offset, text=text))
    return sorted(result, key=lambda cue: (cue['start'], cue['end']))


def retime(timeline):
    audio = timeline.spec['audio']
    captions = timeline.spec.get('captions', {})
    if captions.get('kind') == 'narration':
        if audio.get('voiceover_volume', 1) == 0:
            return []
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
