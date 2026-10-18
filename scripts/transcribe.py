#!/usr/bin/env python3
"""Local, opt-in Whisper transcription with immutable evidence bundles."""
import argparse
import json
import uuid
from pathlib import Path
from pipeline.common import FileLock, PipelineError, read_json, write_json, atomic_write, file_hash, utcnow
from pipeline.captions import timestamp as srt_timestamp, as_srt


def transcribe_job(job, *, model='small.en', language='en', device='cpu', compute_type='int8',
                   vad=True, allow_download=False, model_factory=None):
    job = Path(job).resolve()
    audio = job / 'analysis/voiceover.wav'
    if not audio.is_file():
        raise PipelineError('missing_transcription_audio', 'job', 'No prepared 16 kHz transcription derivative exists.')
    if model_factory is None:
        from faster_whisper import WhisperModel
        model_factory = WhisperModel
    with FileLock(job.with_name('.' + job.name + '.job.lock'), timeout=30):
        identity = file_hash(audio)
        manifest = read_json(job / 'manifest.json') if (job / 'manifest.json').is_file() else {}
        engine = model_factory(model, device=device, compute_type=compute_type, local_files_only=not allow_download)
        raw, info = engine.transcribe(str(audio), language=language or None, vad_filter=vad,
                                      word_timestamps=True, beam_size=5)
        segments = []
        for number, segment in enumerate(raw, 1):
            segments.append({'id': number, 'start': round(segment.start, 3), 'end': round(segment.end, 3),
                'text': segment.text.strip(), 'words': [{'start': round(w.start, 3), 'end': round(w.end, 3),
                    'text': w.word, 'probability': round(w.probability, 4)} for w in (segment.words or [])]})
        if file_hash(audio) != identity:
            raise PipelineError('transcription_input_changed', 'audio', 'Transcription input changed; no transcript was published.')
        bundle = job / 'analysis/transcripts' / uuid.uuid4().hex
        transcript = {'version': 1, 'status': 'complete', 'model': model, 'language': info.language,
            'language_probability': round(info.language_probability, 4), 'duration': round(info.duration, 3),
            'segments': segments, 'audio_sha256': identity, 'source_sha256': manifest.get('clone_sha256', manifest.get('sha256')),
            'created_at': utcnow(), 'download_authorized': allow_download,
            'srt': str(bundle / 'transcript.srt'), 'text_file': str(bundle / 'transcript.txt')}
        text = '\n'.join(f'[{srt_timestamp(s["start"])} - {srt_timestamp(s["end"])}] {s["text"]}' for s in segments)
        atomic_write(bundle / 'transcript.srt', as_srt(segments).encode('utf-8'))
        atomic_write(bundle / 'transcript.txt', text.encode('utf-8'))
        write_json(bundle / 'transcript.json', transcript)
        # JSON is the commit pointer. Readers resolve its immutable bundle paths.
        write_json(job / 'analysis/transcript.json', transcript)
        return transcript


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job', type=Path)
    parser.add_argument('--model', default='small.en')
    parser.add_argument('--language', default='en')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--compute-type', default='int8')
    parser.add_argument('--no-vad', action='store_true')
    parser.add_argument('--allow-download', action='store_true', help='Permit the explicit local model download; otherwise use cache/local paths only')
    args = parser.parse_args(argv)
    try:
        result = transcribe_job(args.job, model=args.model, language=args.language, device=args.device,
            compute_type=args.compute_type, vad=not args.no_vad, allow_download=args.allow_download)
        print(json.dumps({'ok': True, 'segments': len(result['segments']), 'srt': result['srt'], 'text_file': result['text_file']}))
        return 0
    except (PipelineError, OSError, ImportError, ValueError, RuntimeError) as exc:
        print(json.dumps({'ok': False, 'error': exc.as_dict() if isinstance(exc, PipelineError) else {'code': 'transcription_failed', 'message': str(exc)}}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
