# Timeline v1

The runtime contract is `schemas/timeline-v1.schema.json`, generated from `scripts/pipeline/schema.py`. Unknown properties, nonfinite values, invalid enums, malformed ranges, and missing assets are rejected with a field and remediation hint. Version 1 is assumed for legacy `clips` timelines without an explicit version; normalized output includes `version`, `revision`, and stable clip IDs. An editorial `cuts` scaffold is not silently treated as a renderable timeline.

All relative asset and output paths resolve against the timeline JSON, never the process working directory. JSON readers accept UTF-8 with or without a BOM; pipeline writers emit UTF-8 without a BOM. This explicitly supports Windows PowerShell 5.1's `Set-Content -Encoding UTF8` and PowerShell 7's no-BOM variant.

## Generated example

`examples/generate_fixtures.py NEW_DIRECTORY` writes both `minimal.json` and `rich.json` plus their synthetic media. The following illustrates additional optional fields; caption transcripts are supplied separately and must describe the corresponding source audio.

```json
{
  "version": 1,
  "revision": 0,
  "video": {"width": 160, "height": 96, "fps": "30000/1001"},
  "clips": [
    {"id": "intro", "source": "red.mkv", "in": 0, "duration": 1.001,
     "audio": {"mode": "preserve", "stream": 0, "gain": 0.3}},
    {"id": "detail", "source": "green.mkv", "in": 1, "duration": 1.001,
     "audio": {"mode": "mute"}}
  ],
  "audio": {
    "voiceover": "voice.wav",
    "voiceover_volume": 1,
    "music": [{"source": "music.wav", "start": 0, "end": 2,
               "volume": 0.1, "fade_in": 0.2, "fade_out": 0.2}],
    "sfx": [{"source": "effect.wav", "start": 1.5, "duration": 0.3, "volume": 0.5}],
    "ducking": {"enabled": true, "threshold": 0.05, "ratio": 8}
  },
  "overlays": [{"source": "overlay.ppm", "start": 0.5, "duration": 1,
                "width": 64, "x": "center", "y": "center",
                "opacity": 0.8, "fade_in": 0.2, "fade_out": 0.2}],
  "titles": [{"type": "callout", "text": "Chào Sunday: 50%",
              "start": 0.2, "duration": 0.7, "size": 14,
              "x": "center", "y": "top", "color": "white", "box": true}],
  "encode": {"video_codec": "libx264", "preset": "ultrafast", "crf": 18},
  "output": "output/example.mp4"
}
```

## Timing and media

`fps` accepts a positive number or rational string, up to 240. `29.97` means exactly `2997/100`; use `"30000/1001"` for the NTSC rational rate. Each clip duration rounds **once, half-up**, to the nearest output-frame count. A clip rounding to zero frames is rejected. Total duration is the sum of those exact frame counts divided by the rational rate. Frame counts and output average frame rate are checked after encoding. Video dimensions must be even and within the schema's bounds.

Clips are sequential. Video `in` is a source-media timestamp; `duration` is timeline duration. Preflight uses the selected video stream, not a longer narration/container stream, to validate source bounds. Container time-base rounding is allowed only as metadata precision tolerance; each normalized cut still has to decode to the exact expected frame count. There is no implicit freeze-frame/loop extension to conceal missing footage. Still-image clips use `type: "image"`, require `in: 0`, and last their declared frame-grid duration. `zoom` is a centered zoom factor from 1 to 8.

Ranges for overlays, titles, music, and SFX must be positive and contained in the quantized edit. Each fade is at most half its original track/event duration. Explicit coordinates are numeric; named placement uses `center`, `left`, `right`, `top`, or `bottom`. Arbitrary filter expressions are not accepted. Title text is written to UTF-8 files with FFmpeg text expansion disabled; a local per-title `font` or `PIPELINE_FONT` overrides the platform fallback.

## Audio

Every render has a 48 kHz stereo audio bed covering the video duration, including intentional silence. Short narration, music, SFX, and source streams cannot shorten the output. Longer inputs are trimmed. External tracks are not implicitly looped.

Legacy clips default to `audio.mode: "mute"`. Use `preserve` to retain original-quality source audio, `stream` to select a zero-based audio-stream index, and `gain` for linear gain. Missing source audio at the default stream becomes silence; an explicitly invalid stream index fails. Resampling/channel-layout normalization happens at delivery quality, never by reusing the 16 kHz transcription derivative.

Narration is optional. `voiceover_start` places it on the timeline and `voiceover_source_in` seeks its source. Music/SFX accept `source_in`, `volume`, and fades. Optional ducking compresses the background mix against narration; it does not process a nonexistent narration track. Optional `audio.loudness` uses measured two-pass normalization:

```json
{"integrated": -16, "true_peak": -1, "range": 11}
```

The final encoded output is measured again. Silence or a program too short for finite measurements cannot satisfy a loudness target and is rejected instead of being labeled compliant. Disable that target for intentional silence. QA defaults allow 2 LU integrated-target tolerance and 0.3 dB encoded true-peak tolerance; stricter `qa` settings can be supplied.

## Captions

Source captions use each clip's `transcript` JSON and appear only on selected, audible source audio. Reordering/repeating clips repeats/reorders their cues. Cuts use fully contained word timestamps; when only segment timing exists, a partly removed segment is omitted rather than inventing the missing words. SRT timestamps are rebased onto the final edit.

```json
{"mode": "mux", "kind": "source", "language": "en"}
```

`sidecar` writes an immutable SRT next to the QA receipt. `mux` adds mov_text to MP4/MOV or SRT to MKV. `burn` renders captions using FFmpeg's `subtitles` filter/libass; its optional `font` is a safe font-family name, and `size` is a subtitle size. Empty source/narration cue sets cannot be muxed or burned as if they contained evidence. Titles are independent of transcripts.

Narration captions use `kind: "narration"` plus `transcript` and an actual `audio.voiceover`; they follow its source-in and timeline-start offsets, not the source video cuts.

## Output and QA

Supported containers are MP4, MOV, and MKV; delivery uses libx264 video and AAC audio. Default overwrite is an atomic replacement **after** QA; `--no-overwrite` explicitly forbids replacing an existing path. Output lock files are deliberately retained. Never delete one to steal ownership from a running process. On Windows, a player/editor holding the output open may prevent replacement; close it and retry rather than deleting the old deliverable.

Each unique QA receipt records the normalized timeline/revision, source hashes, FFmpeg version, output hash, decoded frame count, rational frame rate, stream durations, optional measurements, and caption sidecar. Default checks require video+audio, exact video frames/rate, duration coverage, and successful full decode. Audio duration tolerance defaults to 60 ms for codec/container framing. Optional `qa` fields are `max_silence_seconds`, `max_black_seconds`, `max_true_peak_db`, `loudness_tolerance_lu`, and `audio_tolerance_seconds`; enabling a threshold makes it a publication gate.

Cached intermediates are lossless FFV1/PCM cut renders, not final compositions. Global overlays, narration, music, ducking, captions, and loudness are rebuilt for every delivery. Cache reuse requires matching source content, cut/audio/video settings, implementation contract, FFmpeg version, and a verified receipt/output hash. `--cache-mib` bounds retained cache media; `--no-cache` uses only temporary intermediates. Active render files, clones, QA history, and footage samples need additional disk space and are not counted as retained cache. Unknown cache directories are never adopted or cleaned implicitly.

Filter graphs live in files. Each cut uses a bounded input command, so hundreds of cuts do not create one enormous Windows command line. The serialized UTF-16 budget is checked before each launch. Excessive *simultaneous* external audio/overlay tracks must be precomposed or use shorter paths; an actionable failure is preferable to an opaque CreateProcess error.
