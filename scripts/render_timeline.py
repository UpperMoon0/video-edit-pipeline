#!/usr/bin/env python3
"""Render a declarative JSON cut timeline with FFmpeg.

Every source path should point to a clone or generated working asset. The script
never writes to or modifies an input file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def resolved(base: Path, value: str) -> Path:
    path = Path(value)
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("timeline", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    timeline_path = args.timeline.resolve()
    base = timeline_path.parent
    spec = json.loads(timeline_path.read_text(encoding="utf-8"))
    width = int(spec.get("video", {}).get("width", 1920))
    height = int(spec.get("video", {}).get("height", 1080))
    fps = int(spec.get("video", {}).get("fps", 30))
    clips = spec["clips"]
    total_duration = sum(float(clip["duration"]) for clip in clips)

    command = ["ffmpeg", "-hide_banner", "-y"]
    for clip in clips:
        duration = f"{float(clip['duration']):.6f}"
        source = str(resolved(base, clip["source"]))
        if clip.get("type", "video") == "image":
            command += ["-loop", "1", "-t", duration, "-i", source]
        else:
            command += [
                "-ss",
                f"{float(clip.get('in', 0)):.6f}",
                "-t",
                duration,
                "-i",
                source,
            ]

    overlays = spec.get("overlays", [])
    overlay_indices = []
    for overlay in overlays:
        overlay_indices.append(len(clips) + len(overlay_indices))
        command += [
            "-loop",
            "1",
            "-t",
            f"{total_duration:.6f}",
            "-i",
            str(resolved(base, overlay["source"])),
        ]

    voice_index = len(clips) + len(overlays)
    command += ["-i", str(resolved(base, spec["audio"]["voiceover"]))]
    music_tracks = spec.get("audio", {}).get("music", [])
    music_indices = []
    for track in music_tracks:
        index = voice_index + 1 + len(music_indices)
        music_indices.append(index)
        duration = float(track["end"]) - float(track["start"])
        command += [
            "-ss",
            f"{float(track.get('source_in', 0)):.6f}",
            "-t",
            f"{duration:.6f}",
            "-i",
            str(resolved(base, track["source"])),
        ]

    sfx_tracks = spec.get("audio", {}).get("sfx", [])
    sfx_indices = []
    for track in sfx_tracks:
        index = voice_index + 1 + len(music_indices) + len(sfx_indices)
        sfx_indices.append(index)
        command += [
            "-ss",
            f"{float(track.get('source_in', 0)):.6f}",
            "-t",
            f"{float(track['duration']):.6f}",
            "-i",
            str(resolved(base, track["source"])),
        ]

    filters = []
    video_labels = []
    for index, clip in enumerate(clips):
        duration = float(clip["duration"])
        zoom = max(float(clip.get("zoom", 1.0)), 1.0)
        scaled_width = round(width * zoom / 2) * 2
        scaled_height = round(height * zoom / 2) * 2
        label = f"v{index}"
        video_labels.append(f"[{label}]")
        filters.append(
            f"[{index}:v]"
            f"scale={scaled_width}:{scaled_height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps},trim=duration={duration:.6f},"
            f"setpts=PTS-STARTPTS,format=yuv420p[{label}]"
        )
    filters.append(
        "".join(video_labels)
        + f"concat=n={len(clips)}:v=1:a=0[basev]"
    )

    current_video = "basev"
    for overlay_number, (overlay, input_index) in enumerate(zip(overlays, overlay_indices)):
        duration = float(overlay["duration"])
        start = float(overlay["start"])
        end = start + duration
        fade_in = min(float(overlay.get("fade_in", 0.5)), duration / 2)
        fade_out = min(float(overlay.get("fade_out", 0.5)), duration / 2)
        fade_out_start = max(end - fade_out, start)
        overlay_label = f"overlay{overlay_number}"
        output_label = f"withoverlay{overlay_number}"
        overlay_width = int(overlay.get("width", 800))
        opacity = float(overlay.get("opacity", 1.0))
        filters.append(
            f"[{input_index}:v]fps={fps},scale={overlay_width}:-1,format=rgba,"
            f"colorchannelmixer=aa={opacity:.4f},"
            f"fade=t=in:st={start:.6f}:d={fade_in:.6f}:alpha=1,"
            f"fade=t=out:st={fade_out_start:.6f}:d={fade_out:.6f}:alpha=1,"
            f"setpts=PTS-STARTPTS[{overlay_label}]"
        )
        x = overlay.get("x", "(main_w-overlay_w)/2")
        y = overlay.get("y", "(main_h-overlay_h)/2")
        filters.append(
            f"[{current_video}][{overlay_label}]"
            f"overlay=x={x}:y={y}:eof_action=pass:enable='between(t,{start:.6f},{end:.6f})'"
            f"[{output_label}]"
        )
        current_video = output_label

    voice_volume = float(spec.get("audio", {}).get("voiceover_volume", 1.0))
    filters.append(
        f"[{voice_index}:a]atrim=duration={total_duration:.6f},asetpts=PTS-STARTPTS,"
        "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"highpass=f=70,lowpass=f=10000,volume={voice_volume:.4f}[voice]"
    )
    audio_labels = ["voice"]
    for track_number, (track, input_index) in enumerate(zip(music_tracks, music_indices)):
        start = float(track["start"])
        duration = float(track["end"]) - start
        fade_in = min(float(track.get("fade_in", 1.0)), duration / 2)
        fade_out = min(float(track.get("fade_out", 1.0)), duration / 2)
        fade_out_start = max(duration - fade_out, 0)
        volume = float(track.get("volume", 0.1))
        label = f"music{track_number}"
        delay_ms = round(start * 1000)
        filters.append(
            f"[{input_index}:a]atrim=duration={duration:.6f},asetpts=PTS-STARTPTS,"
            "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume={volume:.4f},afade=t=in:st=0:d={fade_in:.6f},"
            f"afade=t=out:st={fade_out_start:.6f}:d={fade_out:.6f},"
            f"adelay={delay_ms}:all=1[{label}]"
        )
        audio_labels.append(label)

    for track_number, (track, input_index) in enumerate(zip(sfx_tracks, sfx_indices)):
        start = float(track["start"])
        duration = float(track["duration"])
        fade_in = min(float(track.get("fade_in", 0.0)), duration / 2)
        fade_out = min(float(track.get("fade_out", 0.05)), duration / 2)
        volume = float(track.get("volume", 0.15))
        label = f"sfx{track_number}"
        delay_ms = round(start * 1000)
        chain = (
            f"[{input_index}:a]atrim=duration={duration:.6f},asetpts=PTS-STARTPTS,"
            "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume={volume:.4f}"
        )
        if fade_in > 0:
            chain += f",afade=t=in:st=0:d={fade_in:.6f}"
        if fade_out > 0:
            chain += f",afade=t=out:st={max(duration - fade_out, 0):.6f}:d={fade_out:.6f}"
        chain += f",adelay={delay_ms}:all=1[{label}]"
        filters.append(chain)
        audio_labels.append(label)

    audio_output = "voice"
    if len(audio_labels) > 1:
        filters.append(
            "".join(f"[{label}]" for label in audio_labels)
            + f"amix=inputs={len(audio_labels)}:duration=first:dropout_transition=2:normalize=0,"
            "alimiter=limit=0.95[outa]"
        )
        audio_output = "outa"

    output = resolved(base, spec["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    command += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        f"[{current_video}]",
        "-map",
        f"[{audio_output}]",
        "-c:v",
        spec.get("encode", {}).get("video_codec", "libx264"),
        "-preset",
        spec.get("encode", {}).get("preset", "medium"),
        "-crf",
        str(spec.get("encode", {}).get("crf", 18)),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-r",
        str(fps),
        "-movflags",
        "+faststart",
        "-t",
        f"{total_duration:.6f}",
        str(output),
    ]

    if args.dry_run:
        print(subprocess.list2cmdline(command))
        return
    subprocess.run(command, check=True)
    print(f"Rendered {total_duration:.3f}s to {output}")


if __name__ == "__main__":
    main()
