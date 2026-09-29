#!/usr/bin/env python3
"""Transcribe a prepared job's voice-over WAV to timestamped JSON and SRT."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from faster_whisper import WhisperModel


def srt_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("job", type=Path, help="Prepared job directory")
    parser.add_argument("--model", default="small.en")
    parser.add_argument("--language", default="en")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--no-vad", action="store_true")
    args = parser.parse_args()

    job = args.job.resolve()
    audio = job / "analysis" / "voiceover.wav"
    if not audio.is_file():
        raise SystemExit(f"No transcription-ready audio found: {audio}")

    model = WhisperModel(
        args.model,
        device=args.device,
        compute_type=args.compute_type,
    )
    raw_segments, info = model.transcribe(
        str(audio),
        language=args.language or None,
        vad_filter=not args.no_vad,
        word_timestamps=True,
        beam_size=5,
    )

    segments = []
    srt_blocks = []
    for index, segment in enumerate(raw_segments, start=1):
        words = [
            {
                "start": round(word.start, 3),
                "end": round(word.end, 3),
                "text": word.word,
                "probability": round(word.probability, 4),
            }
            for word in (segment.words or [])
        ]
        entry = {
            "id": index,
            "start": round(segment.start, 3),
            "end": round(segment.end, 3),
            "text": segment.text.strip(),
            "words": words,
        }
        segments.append(entry)
        srt_blocks.append(
            f"{index}\n{srt_timestamp(segment.start)} --> "
            f"{srt_timestamp(segment.end)}\n{entry['text']}\n"
        )

    transcript = {
        "version": 1,
        "status": "complete",
        "model": args.model,
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "duration": round(info.duration, 3),
        "segments": segments,
    }
    analysis = job / "analysis"
    (analysis / "transcript.json").write_text(
        json.dumps(transcript, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (analysis / "transcript.srt").write_text(
        "\n".join(srt_blocks), encoding="utf-8"
    )
    (analysis / "transcript.txt").write_text(
        "\n".join(
            f"[{srt_timestamp(item['start'])} - {srt_timestamp(item['end'])}] "
            f"{item['text']}"
            for item in segments
        ),
        encoding="utf-8",
    )
    print(f"Transcribed {len(segments)} segments to {analysis}")


if __name__ == "__main__":
    main()
