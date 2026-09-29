"""
generate_tts.py — Gemini 3.1 TTS script for the video-edit pipeline.

Usage:
    # From a text file:
    python scripts/generate_tts.py --input script.txt --output voiceover.wav

    # Inline text:
    python scripts/generate_tts.py --text "Hello world" --output out.wav

    # Custom voice (default: Alnilam):
    python scripts/generate_tts.py --input script.txt --output out.wav --voice Kore

Requires:
    pip install google-genai python-dotenv
    GEMINI_API_KEY set in .env (project root) or as an environment variable.
"""

import argparse
import base64
import os
import sys
import wave
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

# ── Constants ─────────────────────────────────────────────────────────────────
DEFAULT_VOICE = "Alnilam"
MODEL = "gemini-3.1-flash-tts-preview"
SAMPLE_RATE = 24000
NUM_CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit PCM


# ── Helpers ───────────────────────────────────────────────────────────────────
def save_pcm_as_wav(pcm_bytes: bytes, output_path: Path) -> None:
    """Wrap raw PCM bytes in a WAV container."""
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(NUM_CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)


def load_api_key() -> str:
    """Load GEMINI_API_KEY from .env or environment."""
    # Walk up from CWD to find the nearest .env
    search = Path.cwd()
    for parent in [search, *search.parents]:
        env_file = parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            break
    else:
        load_dotenv()  # fallback: load from CWD

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        sys.exit("ERROR: GEMINI_API_KEY not found in .env or environment.")
    return key


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a voiceover WAV using Gemini 3.1 TTS."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", "-i", type=Path,
                       help="Path to a plain-text script file.")
    group.add_argument("--text", "-t", type=str,
                       help="Inline script text (quote it in the shell).")
    parser.add_argument("--output", "-o", type=Path, required=True,
                        help="Output WAV file path.")
    parser.add_argument("--voice", "-v", type=str, default=DEFAULT_VOICE,
                        help=f"Prebuilt voice name (default: {DEFAULT_VOICE}).")
    args = parser.parse_args()

    # Resolve script text
    if args.input:
        if not args.input.exists():
            sys.exit(f"ERROR: Input file not found: {args.input}")
        script = args.input.read_text(encoding="utf-8").strip()
    else:
        script = args.text.strip()

    if not script:
        sys.exit("ERROR: Script text is empty.")

    api_key = load_api_key()
    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Model : {MODEL}")
    print(f"Voice : {args.voice}")
    print(f"Output: {output_path.resolve()}")
    print("Calling Gemini TTS API...")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=MODEL,
        contents=script,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=args.voice
                    )
                )
            ),
        ),
    )

    audio_part = response.candidates[0].content.parts[0].inline_data
    raw_bytes = audio_part.data

    # Handle both raw bytes and base64-encoded strings
    pcm_data = base64.b64decode(raw_bytes) if isinstance(raw_bytes, str) else raw_bytes

    save_pcm_as_wav(pcm_data, output_path)

    duration_sec = len(pcm_data) / (SAMPLE_RATE * SAMPLE_WIDTH)
    print(f"Done. Duration ~ {duration_sec:.1f}s  ({output_path.resolve()})")


if __name__ == "__main__":
    main()
