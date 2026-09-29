# Video Edit Pipeline

A local-first, non-destructive pipeline for ingesting footage, preparing evidence, editing versioned timelines, and publishing QA-checked video. Windows PowerShell entry points and the cross-platform Python JSON CLI share the same implementation. Original media is never edited in place.

The pipeline supports exact-frame cuts, still images, source-audio selection, optional narration, music/SFX, ducking, measured loudness normalization, image overlays, typed titles/callouts, source/narration captions, range previews, and local shot/transcript search. It does **not** upload footage to a model, infer arbitrary visual descriptions, download transcription models, or spend provider credits automatically.

## Install

Use Python 3.10–3.13 and FFmpeg/FFprobe 6.1 or newer with H.264, FFV1, AAC, and the required filters. PowerShell wrappers support Windows PowerShell 5.1 and PowerShell 7. See [testing and compatibility](docs/TESTING.md) for the actual matrix and optional-feature boundaries.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path config.json)) { Copy-Item config.example.json config.json }
```

Edit `config.json` to select your inbox directories. Put `ffmpeg` and `ffprobe` on PATH, or set `PIPELINE_FFMPEG` and `PIPELINE_FFPROBE` to absolute executable paths. `PIPELINE_PYTHON` selects a Python interpreter for the wrappers; otherwise they prefer this checkout's virtual environment, then PATH. `PIPELINE_FONT` optionally selects a local fallback font for titles.

```powershell
.\scripts\MediaPipeline.ps1 -Action Doctor
.\scripts\MediaPipeline.ps1 -Action Setup
.\scripts\MediaPipeline.ps1 -Action Ingest -SourcePath 'C:\Media\Inbox\recording.mkv'
.\scripts\MediaPipeline.ps1 -Action List
.\scripts\MediaPipeline.ps1 -Action LatestReady
```

`Doctor` does not download models or call a provider. `Setup` initializes directories and the local SQLite registry. Relative inbox paths resolve against the configuration file. Missing tools, unsupported values, and failed stages produce structured errors rather than a false success marker.

## Prepare, edit, render

Successful ingest creates a stable job ID and a full-SHA-256-verified read-only clone. It prepares probe data, samples/contact sheets, a 16 kHz **transcription-only** audio derivative when audio exists, and a minimal timeline for video sources. The renderer reads delivery audio from the original-quality clone, not the transcription derivative.

```powershell
$python = '.\.venv\Scripts\python.exe'
$ready = (& $python scripts/pipeline.py latest-ready | ConvertFrom-Json).result
$timeline = Join-Path $ready.job_path 'edit\timeline.json'
& $python scripts/render_timeline.py $timeline --validate
& $python scripts/render_timeline.py $timeline --preflight
& $python scripts/render_timeline.py $timeline --dry-run
& $python scripts/render_timeline.py $timeline
```

`READY.txt` means **preparation completed**, not that speech was transcribed, editorial decisions were made, or a final render passed QA. Audio-only jobs intentionally have no video timeline or contact sheet. Silent footage has an explicit `no_audio` transcript status.

Renders use bounded lossless cut intermediates, external filter graphs, and a full-duration audio bed. A unique output sibling is encoded and decoded for validation. Only a successful QA result permits atomic replacement of the deliverable. Same-path, symlink, and hard-link input/output aliases are rejected. Failure and cancellation preserve the previous published video.

See [timeline format and examples](docs/TIMELINE.md), [the JSON CLI and editing controls](docs/API.md), and [operations/recovery](docs/OPERATIONS.md).

## Reproducible synthetic examples

Generate fixtures in a **new or empty directory outside the checkout**. Existing files are never overwritten by the fixture generator.

```powershell
& $python examples/generate_fixtures.py 'C:\Media\Pipeline-Demo-New'
& $python scripts/render_timeline.py 'C:\Media\Pipeline-Demo-New\minimal.json' --preflight
& $python scripts/render_timeline.py 'C:\Media\Pipeline-Demo-New\minimal.json'
& $python scripts/render_timeline.py 'C:\Media\Pipeline-Demo-New\rich.json'
```

On Linux, substitute `.venv/bin/python` and a writable media/work directory. Long-media work needs disk space for a verified source clone and active render intermediates; do not place it on a nearly-full temporary filesystem.

## Optional transcription and speech generation

```powershell
& $python -m pip install -r requirements-optional.txt
& $python scripts/transcribe.py $ready.job_path --model small.en --language en --allow-download
& $python scripts/generate_tts.py --input 'C:\Media\script.txt' --output 'C:\Media\narration.wav' --allow-paid
```

Without `--allow-download`, transcription uses an existing model cache or a local model path only. The canonical transcript JSON points to an immutable SRT/text bundle. Gemini TTS requires `GEMINI_API_KEY`, an explicit `--allow-paid` authorization, and a generateContent-compatible PCM/WAV TTS model. Its model and voice are configurable. Script text is submitted to that provider; footage is not. The default legacy model identifier is not a promise of ongoing provider availability. Non-STOP responses, malformed audio, truncated samples, and unsupported formats are rejected before publication. No paid/provider call is part of CI.

`generate_cinematic_sfx.py OUTPUT_DIRECTORY` remains a local standard-library-only utility for synthetic whoosh/riser/impact/click WAVs.

## Watcher

```powershell
.\scripts\Install-Watcher.ps1 -Action Install -StartNow
.\scripts\Install-Watcher.ps1 -Action Status
.\scripts\Install-Watcher.ps1 -Action Stop
.\scripts\Install-Watcher.ps1 -Action Start
.\scripts\Install-Watcher.ps1 -Action Remove
```

Each checkout has its own task name and captures absolute Python/FFmpeg paths. Scheduled execution uses the installing interactive Windows account, not SYSTEM or a remote service account. `Stop` requests cooperative shutdown; use `Status` to observe completion. Removing the task preserves jobs and media. The old unscoped `CodexVideoMediaInbox` task is not silently adopted or removed. See the [migration and recovery guide](docs/OPERATIONS.md).

## Privacy, licensing, contribution

The repository is deny-by-default: only reusable source, schemas, synthetic-example generators, tests, and documentation are allowed. Jobs, state, logs, models, media, credentials, reports, narration, and project-specific editorial work remain local. A QA report includes local source paths and hashes; do not publish it unreviewed.

The pipeline source is available under the maintainer-selected [MIT license](LICENSE). Third-party media, fonts, FFmpeg builds, and generated speech remain subject to their own applicable terms. See [CONTRIBUTING.md](CONTRIBUTING.md) and the [review remediation map](docs/REMEDIATION.md).
