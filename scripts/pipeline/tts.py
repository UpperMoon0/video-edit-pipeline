"""Validate generateContent TTS responses before publishing narration."""
import base64
import binascii
import hashlib
import io
import uuid
import wave
from pathlib import Path
from .common import PipelineError, output_transaction, write_json, utcnow, file_hash


def field(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def extract_audio(response, maximum_bytes=100 * 1024 * 1024):
    candidates = field(response, 'candidates') or []
    if len(candidates) != 1:
        raise PipelineError('tts_candidates', 'response.candidates', 'Expected exactly one completed TTS candidate.')
    candidate = candidates[0]
    reason = field(candidate, 'finish_reason', field(candidate, 'finishReason'))
    reason = field(reason, 'value', reason)
    if reason != 'STOP':
        raise PipelineError('tts_incomplete', 'response.finish_reason', f'TTS did not finish normally ({reason}).', 'Shorten the script or retry explicitly; partial speech was not published.')
    parts = field(field(candidate, 'content'), 'parts') or []
    chunks, parameters, mime_types = [], None, []
    for part in parts:
        inline = field(part, 'inline_data', field(part, 'inlineData'))
        if inline is None:
            continue
        mime = field(inline, 'mime_type', field(inline, 'mimeType', ''))
        if not isinstance(mime, str) or not mime.lower().startswith('audio/'):
            continue
        raw = field(inline, 'data')
        if isinstance(raw, str):
            if len(raw) > maximum_bytes * 4 // 3 + 8:
                raise PipelineError('tts_size', 'response.audio', 'Audio exceeds the configured size limit.')
            try:
                raw = base64.b64decode(raw, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise PipelineError('tts_base64', 'response.audio', 'Invalid base64 audio data.') from exc
        if not isinstance(raw, (bytes, bytearray)) or not raw:
            raise PipelineError('tts_empty_audio', 'response.audio', 'Audio bytes are missing or empty.')
        if len(raw) > maximum_bytes:
            raise PipelineError('tts_size', 'response.audio', 'Audio exceeds the configured size limit.')
        pieces = [piece.strip() for piece in mime.lower().split(';')]
        options = dict(p.split('=', 1) for p in pieces[1:] if '=' in p)
        if pieces[0] in ('audio/wav', 'audio/x-wav', 'audio/wave'):
            try:
                with wave.open(io.BytesIO(raw), 'rb') as wav:
                    if wav.getcomptype() != 'NONE':
                        raise ValueError('Compressed WAV is unsupported')
                    current = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
                    count = wav.getnframes()
                    raw = wav.readframes(count)
                    if len(raw) != count * current[1] * current[2]:
                        raise ValueError('Truncated WAV payload')
            except (wave.Error, EOFError, ValueError) as exc:
                raise PipelineError('tts_wav', 'response.audio', str(exc)) from exc
        elif pieces[0] in ('audio/l16', 'audio/pcm'):
            # Legacy generateContent TTS uses signed 16-bit LE PCM. Unlike the
            # older script, the sample rate comes from the provider MIME header.
            if pieces[0] == 'audio/pcm' and options.get('codec') != 'pcm_s16le' and options.get('format') != 's16le':
                raise PipelineError('tts_format', 'response.mime_type', 'Generic audio/pcm must explicitly declare signed 16-bit little-endian samples.')
            if options.get('codec', 'pcm') not in ('pcm', 'pcm_s16le') or 'rate' not in options:
                raise PipelineError('tts_format', 'response.mime_type', 'Expected PCM with an explicit rate parameter.')
            try:
                current = (int(options['rate']), int(options.get('channels', '1')), 2)
            except ValueError as exc:
                raise PipelineError('tts_format', 'response.mime_type', 'Invalid PCM rate/channel parameters.') from exc
        else:
            raise PipelineError('tts_format', 'response.mime_type', f'Unsupported audio format: {mime}', 'Use a PCM or WAV generateContent TTS model.')
        if not 8000 <= current[0] <= 192000 or not 1 <= current[1] <= 8 or current[2] not in (1, 2, 3, 4):
            raise PipelineError('tts_format', 'response.audio', 'Unsupported PCM parameters.')
        if not raw or len(raw) % (current[1] * current[2]):
            raise PipelineError('tts_alignment', 'response.audio', 'PCM data ends inside a sample frame.')
        if parameters is not None and parameters != current:
            raise PipelineError('tts_format_change', 'response.audio', 'Audio format changed between response parts.')
        parameters = current
        chunks.append(bytes(raw))
        mime_types.append(mime)
        if sum(map(len, chunks)) > maximum_bytes:
            raise PipelineError('tts_size', 'response.audio', 'Combined audio exceeds the configured size limit.')
    if not chunks:
        raise PipelineError('tts_no_audio', 'response.content', 'Completed response contained no audio parts.')
    return b''.join(chunks), parameters, mime_types


def publish_response(response, output, *, model, voice, text, inputs=()):
    pcm, (rate, channels, width), mime_types = extract_audio(response)
    output = Path(output).resolve()
    if output.suffix.lower() != '.wav':
        raise PipelineError('tts_output', 'output', 'TTS output must use a .wav extension.')
    with output_transaction(output, inputs) as temp:
        with wave.open(str(temp), 'wb') as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(width)
            wav.setframerate(rate)
            wav.writeframes(pcm)
        with wave.open(str(temp), 'rb') as wav:
            if wav.getnframes() * channels * width != len(pcm):
                raise PipelineError('tts_validation', 'output', 'WAV frame count does not match the completed PCM response.')
        provenance = output.parent / '.pipeline-provenance' / (uuid.uuid4().hex + '.json')
        report = {'version': 1, 'model': model, 'voice': voice, 'completion': 'STOP', 'created_at': utcnow(),
            'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'text_characters': len(text),
            'output_sha256': file_hash(temp), 'output': str(output), 'sample_rate': rate,
            'channels': channels, 'sample_width': width, 'mime_types': mime_types,
            'duration': len(pcm) / (rate * channels * width)}
        write_json(provenance, report)
    return {**report, 'provenance': str(provenance)}
