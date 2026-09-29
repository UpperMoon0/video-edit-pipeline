"""Single schema definition used by runtime validation and exported JSON Schema."""
from __future__ import annotations


def obj(properties, required=()):
    return dict(type='object', properties=properties, required=list(required), additionalProperties=False)


def number(low=0, high=None, positive=False):
    out = {'type': 'number', 'exclusiveMinimum' if positive else 'minimum': low}
    if high is not None:
        out['maximum'] = high
    return out


def integer(low=0, high=None):
    out = number(low, high)
    out['type'] = 'integer'
    return out


def choice(*values):
    return {'enum': list(values)}


def array(items, **kwargs):
    return dict(type='array', items=items, **kwargs)


PATH = {'type': 'string', 'minLength': 1, 'pattern': '^[^\\u0000\\r\\n]+$'}
TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 10000}
POSITION = {'anyOf': [number(-32768, 32768), choice('center', 'left', 'right', 'top', 'bottom',
    '(main_w-overlay_w)/2', '(main_h-overlay_h)/2')]}
AUDIO_POLICY = obj({'mode': choice('mute', 'preserve'), 'stream': integer(0, 63), 'gain': number(0, 16)})
CLIP = obj({'id': PATH, 'source': PATH, 'type': choice('video', 'image'), 'in': number(),
    'duration': number(0, 86400, True), 'zoom': number(1, 8), 'audio': AUDIO_POLICY,
    'transcript': PATH, 'asset_id': PATH}, ['source', 'duration'])
TRACK_FIELDS = {'source': PATH, 'start': number(), 'source_in': number(), 'volume': number(0, 16),
    'fade_in': number(), 'fade_out': number()}
OVERLAY = obj({'source': PATH, 'start': number(), 'duration': number(0, 86400, True),
    'width': integer(1, 7680), 'opacity': number(0, 1), 'fade_in': number(), 'fade_out': number(),
    'x': POSITION, 'y': POSITION}, ['source', 'start', 'duration'])
TITLE = obj({'type': choice('title', 'callout'), 'text': TEXT, 'start': number(),
    'duration': number(0, 86400, True), 'x': POSITION, 'y': POSITION, 'font': PATH,
    'size': integer(8, 512), 'color': {'type': 'string', 'pattern': '^(white|black|red|yellow|blue|green|#[0-9A-Fa-f]{6})$'},
    'box': {'type': 'boolean'}}, ['text', 'start', 'duration'])
CAPTIONS = obj({'mode': choice('sidecar', 'mux', 'burn'), 'kind': choice('source', 'narration'),
    'transcript': PATH, 'language': {'type': 'string', 'pattern': '^[A-Za-z]{2,3}$'},
    'font': {'type': 'string', 'pattern': '^[A-Za-z0-9 _-]+$'}, 'size': integer(8, 128)})
QA = obj({'max_silence_seconds': number(), 'max_black_seconds': number(),
    'max_true_peak_db': number(-20, 0), 'loudness_tolerance_lu': number(0, 10),
    'audio_tolerance_seconds': number(0, .2)})
SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    '$id': 'https://github.com/UpperMoon0/video-edit-pipeline/schemas/timeline-v1.schema.json',
    'title': 'Video Edit Pipeline timeline v1',
    **obj({'version': {'const': 1}, 'revision': integer(), 'output': PATH,
        'video': obj({'width': integer(16, 7680), 'height': integer(16, 4320),
            'fps': {'anyOf': [number(0, 240, True), {'type': 'string', 'pattern': '^[0-9]+([./][0-9]+)?$'}]}}),
        'clips': array(CLIP, minItems=1, maxItems=10000), 'overlays': array(OVERLAY), 'titles': array(TITLE),
        'audio': obj({'voiceover': PATH, 'voiceover_volume': number(0, 16),
            'voiceover_start': number(), 'voiceover_source_in': number(),
            'music': array(obj({**TRACK_FIELDS, 'end': number(0, 86400, True)}, ['source', 'start', 'end'])),
            'sfx': array(obj({**TRACK_FIELDS, 'duration': number(0, 86400, True)}, ['source', 'start', 'duration'])),
            'ducking': obj({'enabled': {'type': 'boolean'}, 'threshold': number(.00097563, 1), 'ratio': number(1, 20)}),
            'loudness': obj({'integrated': number(-36, -5), 'true_peak': number(-9, 0), 'range': number(1, 20)}, ['integrated', 'true_peak'])}),
        'captions': CAPTIONS,
        'encode': obj({'video_codec': choice('libx264'),
            'preset': choice('ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'),
            'crf': integer(0, 51)}), 'qa': QA, 'metadata': {'type': 'object'}}, ['clips', 'output'])
}
