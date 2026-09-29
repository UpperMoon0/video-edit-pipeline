#!/usr/bin/env python3
"""Opt-in Gemini generateContent TTS; incomplete responses never replace audio."""
import argparse
import json
import os
from pathlib import Path
from pipeline.common import PipelineError, reject_alias
from pipeline.tts import extract_audio, publish_response

MODEL = 'gemini-3.1-flash-tts-preview'
DEFAULT_VOICE = 'Alnilam'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--input', '-i', type=Path)
    inputs.add_argument('--text', '-t')
    parser.add_argument('--output', '-o', type=Path, required=True)
    parser.add_argument('--voice', '-v', default=DEFAULT_VOICE)
    parser.add_argument('--model', default=MODEL, help='A generateContent-compatible PCM/WAV TTS model')
    parser.add_argument('--allow-paid', action='store_true', help='Explicitly authorize this one provider request')
    parser.add_argument('--max-text-chars', type=int, default=5000)
    args = parser.parse_args()
    try:
        text = args.input.read_text(encoding='utf-8-sig').strip() if args.input else args.text.strip()
        if not text or args.max_text_chars < 1 or len(text) > args.max_text_chars:
            raise PipelineError('tts_text_budget', 'input', 'Script is empty or exceeds the explicitly configured character limit.')
        if args.output.suffix.lower() != '.wav':
            raise PipelineError('tts_output', 'output', 'TTS output must use a .wav extension.')
        reject_alias(args.output.resolve(), [args.input.resolve()] if args.input else [])
        if not args.allow_paid:
            raise PipelineError('paid_request_not_authorized', 'allow-paid', 'No provider request was sent.', 'Add --allow-paid to authorize one request; text is submitted to Gemini.')
        from dotenv import load_dotenv
        load_dotenv()
        key = os.environ.get('GEMINI_API_KEY')
        if not key:
            raise PipelineError('missing_credential', 'GEMINI_API_KEY', 'API key is not configured.')
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=key)
        try:
            response = client.models.generate_content(model=args.model, contents=text,
                config=types.GenerateContentConfig(response_modalities=['AUDIO'],
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=args.voice)))))
        except Exception as exc:
            raise PipelineError('provider_failed', 'gemini', 'Provider request failed; no audio was published.',
                'Check account/model availability. Provider exception details are omitted to avoid credential or text disclosure.') from exc
        result = publish_response(response, args.output, model=args.model, voice=args.voice, text=text,
                                  inputs=[args.input.resolve()] if args.input else [])
        print(json.dumps({'ok': True, **result}))
        return 0
    except (PipelineError, ImportError, OSError) as exc:
        error = exc.as_dict() if isinstance(exc, PipelineError) else {'code': 'environment', 'message': str(exc)}
        print(json.dumps({'ok': False, 'error': error}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
