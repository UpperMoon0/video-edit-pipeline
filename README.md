# Video Edit Pipeline

This pipeline lets Codex work with local media without a chat attachment.

## Setup

Requires Windows PowerShell, Python 3.10+, and FFmpeg with `ffmpeg` and `ffprobe` on PATH.
Run these commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.json config.json
```

Edit `config.json` to set your own inbox paths before running Setup. Keep this local
configuration private. Transcription downloads the selected Whisper model on first use.
Optional Gemini speech generation requires `GEMINI_API_KEY` in your environment or a
local `.env` file and access to the model configured in `generate_tts.py`.

## Drop folder

Copy or save source media into this folder:

- `C:\Media\Inbox`

The watcher waits for the file to stop changing, then creates an isolated job in
`jobs`. It never moves, renames, deletes, or edits the incoming original.

Each job contains:

- `source/`: a hash-verified, read-only clone of the source media
- `analysis/probe.json`: stream, codec, resolution, and duration metadata
- `analysis/voiceover.wav`: mono 16 kHz transcription-ready audio
- `analysis/contact-sheet.jpg`: sixteen evenly sampled frames
- `analysis/transcript.json`: placeholder for timestamped transcription
- `edit/timeline.json`: reusable declarative cut-list scaffold
- `output/`: rendered deliverables
- `manifest.json`: provenance and SHA-256 verification
- `READY.txt`: completion marker and next instruction

When preparation finishes, Windows displays a **Codex video is ready** notification.
You can then tell Codex: **Use the latest inbox video.**

## Commands

```powershell
# One-time setup
.\scripts\MediaPipeline.ps1 -Action Setup

# Clone and analyze one known file immediately
.\scripts\MediaPipeline.ps1 -Action Ingest -SourcePath 'D:\footage\clip.mp4'

# List media currently waiting in configured inboxes
.\scripts\MediaPipeline.ps1 -Action Discover

# Run the watcher in the foreground
.\scripts\MediaPipeline.ps1 -Action Watch

# Timestamped local transcription (after ingest)
.\.venv\Scripts\python.exe .\scripts\transcribe.py .\jobs\JOB_NAME

# Dense, seek-based footage sampling for editorial review
.\scripts\Sample-Video.ps1 -InputPath .\jobs\JOB_NAME\source\clip.mp4 -OutputDirectory .\jobs\JOB_NAME\analysis\samples -IntervalSeconds 10

# Render a reusable JSON cut timeline
.\.venv\Scripts\python.exe .\scripts\render_timeline.py .\projects\PROJECT\timeline.json

# Install/remove the watcher as a per-user logon task
.\scripts\Install-Watcher.ps1
.\scripts\Install-Watcher.ps1 -Remove
```

The edit itself is represented in `edit/timeline.json`, so later projects can use
the same rendering code with a different transcript and cut list.

## Reusable tools

- `MediaPipeline.ps1`: watch, discover, clone, and analyze incoming media.
- `Install-Watcher.ps1`: install or remove the per-user Windows watcher task.
- `Sample-Video.ps1`: create contact sheets from footage.
- `transcribe.py`: generate timestamped JSON, SRT, and text transcripts.
- `render_timeline.py`: render JSON timelines with clips, overlays, voiceover, music, and SFX.
- `generate_tts.py`: generate a voiceover from supplied text using Gemini.
- `generate_cinematic_sfx.py`: optional procedural sound-effect generator.

The ingest timeline is an editorial scaffold. Before rendering, provide a `clips`
array (each with `source`, `duration`, and optional `in`), `audio.voiceover`, and
`output`. The renderer does not consume the scaffold's `cuts` field. Asset paths
are relative to the timeline file unless absolute.

## Local project data

Only explicitly allowed pipeline files are tracked. Media, video-specific projects,
jobs, transcripts, renders, logs, state, reference-analysis notes, virtual environments,
local configuration, and `.env` files remain local. Store edit assets and timelines
under `projects/` or `jobs/`. Review the allowlist in `.gitignore` when adding reusable
pipeline source files.
