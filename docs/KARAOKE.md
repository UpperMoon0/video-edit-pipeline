# Faster karaoke and sing-along production

Use one private project for the downloaded source, supplied lyrics, translations,
syllable timing, style and source credits. Align once, revise the translation or
subtitle look without rerunning models, approve a short preview, then export the
vocal and vocal-reduced versions. Instrumental delivery reuses the finished
picture rather than encoding the entire animation again.

## What is implemented

`scripts/karaoke.py` provides `init`, `align`, `build`, `preview`, `render`,
`separate` and `remux`. The normal build/render path needs only core dependencies
and FFmpeg with libass. The current visual preset supports 16:9 landscape sources
with constant frame rate. Other aspect ratios/VFR sources must first be prepared
using the existing timeline renderer. Translations and source research are
editorial inputs; the CLI does not invent translations, retrieve lyrics, resolve
rights, authenticate a channel, or upload videos.

The preset puts English above larger romanized karaoke text, with warm gold
highlights, generous inset margins, a rounded translucent charcoal panel and a
soft shadow. The panel fades over 200 ms, joins nearby vocal cues, and disappears
across instrumental breaks. All design elements are embedded in ASS; no external
background PNG or full-frame per-pixel opacity expression is needed.

## One-time setup

Keep the private project and models **outside this public checkout**, or under
the existing ignored `jobs/` directory. Core rendering uses the main environment.
Use a dedicated Python environment for optional models; do not repair or upgrade
the system environment as part of a video job.

```powershell
# CPU alignment + optional CPU separation. Python 3.13 was used in local production.
python -m venv 'C:\Media\KaraokeTools'
& 'C:\Media\KaraokeTools\Scripts\python.exe' -m pip install -r requirements-karaoke.txt
```

For Windows DirectML, use a separate environment with `onnxruntime-directml`
instead of `onnxruntime`; install `jsonschema`, `numpy`, `scipy`, `faster-whisper`
and `pypinyin` there. CUDA requires a compatible `onnxruntime-gpu` build and its
vendor libraries. Never install competing ONNX Runtime variants into the same
environment. `separate --provider directml` fails clearly if that provider is
unavailable rather than silently switching the requested mode to CPU.

The lightweight MDX path does **not** require torch, torchvision, torchaudio,
librosa or the full audio-separator package. Installing those packages just for
this path caused avoidable large downloads during the initial production.

Download a compatible instrumental-primary model once from the
[UVR model publisher](https://github.com/TRvlvr/model_repo/releases/tag/all_public_uvr_models),
for example `UVR-MDX-NET-Inst_HQ_3.onnx`, plus the publisher's
[MDX configuration registry](https://github.com/TRvlvr/application_data/blob/main/mdx_model_data/model_data_new.json).
Store both locally and retain their source URLs and hashes in the private job.
The separator matches the UVR model's tail-MD5 configuration and records its
full SHA-256; models expecting vocals as their primary output are rejected.
No separation command performs a model or package download.

On the original GTX 1050 Ti setup, DirectML completed the approximately three-minute
source in about 87 seconds; CPU processing was much slower. That is a measured
production observation, not a speed guarantee. Float16 Whisper inference was
unsupported on that GPU/backend combination; CPU int8 alignment worked. Always
verify the actual installed provider rather than assuming NVIDIA implies usable
CUDA acceleration. [ONNX Runtime DirectML](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html)

## Prepare a project

Download exactly one video to a private directory. Preserve the original-quality
stereo audio; the pipeline's 16 kHz mono transcription derivative is for alignment
only, never the backing-track master. If using yt-dlp, use `--no-playlist`, a
stable ID-based output name, and retain its metadata JSON. A JavaScript-runtime
warning can affect extraction; a successful download still needs stream checks.

```powershell
python scripts/karaoke.py init 'C:\Media\Song\source.mp4' 'C:\Media\Song\karaoke.json' --title 'Song | Pinyin + English'
```

Edit the generated JSON. The schema is
[`karaoke-v1.schema.json`](../schemas/karaoke-v1.schema.json). Example original,
synthetic cue data:

```json
{
  "version": 1,
  "title": "Synthetic sing-along",
  "source": "source.mp4",
  "language": "en",
  "style": {"font": "Arial", "translation_font": "Arial", "panel": true},
  "credits": [],
  "cues": [{
    "start": 0.5, "end": 1.5,
    "text": "Light and sound",
    "translation": "Light and sound",
    "syllables": [
      {"text": "Light", "start": 0.5, "end": 0.8},
      {"text": "and", "start": 0.8, "end": 1.1},
      {"text": "sound", "start": 1.1, "end": 1.5}
    ]
  }]
}
```

For Chinese, set `language` to `zh`; pinyin is the appropriate romanization.
Romaji is Japanese. Remove copied website menus, ads and unrelated Japanese text
before preparing cues. Use the words provided for the task as the lyric authority.
Keep a separate occurrence for each repeated chorus; the source's actual order
may differ from a lyrics page and a sped-up edit changes all original timings.
Split long sentences at natural phrase boundaries before alignment. Add one
English translation per displayed line.

Manual `syllables` work without optional dependencies. Every start/end uses
seconds in the **downloaded source's clock**. Cue and syllable ranges must be
positive, ordered and contained; ASS requires centisecond precision. The build
warns about long text, but font fallback and exact glyph widths still require
visual review. Installed fonts are used; fonts are not downloaded or bundled.

For automatic Chinese alignment, supply rough `start`/`end` bounds and Chinese
`text`, omit `syllables`, and optionally supply a `romanization` array with one
pinyin syllable per Chinese character. Explicit readings override generated
pronunciation. This matters for polyphonic characters and sung pronunciation.

```powershell
# First use only: permit the local model download explicitly.
& 'C:\Media\KaraokeTools\Scripts\python.exe' scripts/karaoke.py align 'C:\Media\Song\karaoke.json' --model small --allow-download
# Later uses stay local; a missing model produces an error.
& 'C:\Media\KaraokeTools\Scripts\python.exe' scripts/karaoke.py align 'C:\Media\Song\karaoke.json' --model small
```

Alignment groups nearby supplied lines into windows up to 25 seconds and matches
them against the source audio. It does not replace the lyrics with ASR guesses.
The saved timing is bound to the source hash and lyric text/ranges. Translation
and style edits preserve that timing. Changed source lyrics/ranges require an
explicit realignment. Review chorus starts, sustained syllables, collapsed timing
and pronunciation; automatic alignment is not proof of perfect synchronization.

## Build, preview and export

```powershell
python scripts/karaoke.py build 'C:\Media\Song\karaoke.json'
python scripts/karaoke.py preview 'C:\Media\Song\karaoke.json' 'C:\Media\Song\preview.mp4' --start 25 --duration 8
python scripts/karaoke.py render 'C:\Media\Song\karaoke.json' 'C:\Media\Song\sing-along.mp4'
# Optional, only after verifying this encoder on the machine:
python scripts/karaoke.py render 'C:\Media\Song\karaoke.json' 'C:\Media\Song\sing-along.mp4' --encoder h264_nvenc
```

Build returns a content-addressed private `.karaoke/IDENTITY/` folder containing
ASS, bilingual SRT, descriptions for both versions and a build record. Identity
includes project contents, source hash and preset version. Model packages are not
imported by `build`, `preview` or `render`. Save a preview with the longest lyric
and a busy shot, then inspect an instrumental break. English should remain above
the karaoke line; the panel should not clip text, cover faces unnecessarily or
linger through a long break. Preview timing stays in the source clock, including
the highlighted portion of a line that began before the preview.

Rendering validates frame count, frame rate, stream duration and full decode
before atomic replacement of the final MP4. Failure preserves a previous master.
Source aliases, including hard links, are rejected. Source media is hashed again
before publication. This is media QA, not an automated aesthetic review.

## Make the instrumental version

```powershell
& 'C:\Media\KaraokeTools\Scripts\python.exe' scripts/karaoke.py separate 'C:\Media\Song\source.mp4' 'C:\Media\Song\instrumental.wav' --model 'C:\Media\Models\UVR-MDX-NET-Inst_HQ_3.onnx' --model-data 'C:\Media\Models\mdx_model_data.json' --provider cpu
python scripts/karaoke.py remux 'C:\Media\Song\sing-along.mp4' 'C:\Media\Song\instrumental.wav' 'C:\Media\Song\instrumental-karaoke.mp4'
```

Use `--provider directml` in the DirectML environment when validated. The separator
uses overlapping spectral windows and polarity averaging, preserves source sample
count, checks finite output and limits the separated peak. Listen to both a quiet
verse and a loud chorus for vocal leakage, missing instruments or watery artifacts.
Measure correlation/lag against a music-only passage when available; expected
duration alone does not prove alignment or separation quality.

Remux accepts replacement audio within 0.1 seconds of picture duration, pads only
the small codec tail, copies the video stream, and verifies the encoded picture
packet hash before and after. It decodes the final result and checks both stream
durations. Keep the vocal and vocal-reduced exports as separate files.

## Credits, description and publication

Each `credits` entry has `role`, `name` and `url`. Roles are `animation_creator`,
`original_video`, `music`, `remix` and `reupload`. Credit the creator's own verified
page/upload before the reupload used for ingestion. Check watermarks, descriptions
and the creator's page; do not assume a YouTube uploader made the animation.
Credit the song/artist separately from the visuals. Credit a remix producer only
when verified; do not invent one because the recording is sped up.

Description output groups these roles, clearly labels reuploads, and uses
**“Vocals reduced for karaoke.”** for instrumental versions. Keep public copy
focused on the song, sing-along experience and credits. Do not mention AI or
model/provider implementation details in the description. Private production
records can retain those technical details for reproducibility.

Upload through the user's requested browser/service only when authorized. Verify
the exact channel handle/ID immediately before transfer; the active account can
change between browser tabs. Title the instrumental version distinctly and
publish it as a separate video when requested. Confirm the selected visibility,
save the full source links in the description, and retain the published URL and
observed copyright-check outcome in the private job. Do not create a duplicate
upload just because processing is slow. Capture a screenshot of the publication
result and verify the saved attribution.

Credit and vocal reduction do not establish usage rights. A music claim can still
occur on the instrumental version. Record what Studio actually reports, separating
a claim, strike, reach restriction and potential earnings limitation. A successful
upload or initial check is not evidence of monetization eligibility. Review
[YouTube's current guidance](https://support.google.com/youtube/answer/6013276)
when advising about those outcomes.

## Synthetic smoke test

```powershell
python examples/generate_karaoke.py 'C:\Media\Karaoke-Demo-New'
python scripts/karaoke.py render 'C:\Media\Karaoke-Demo-New\karaoke.json' 'C:\Media\Karaoke-Demo-New\master.mp4'
python scripts/karaoke.py remux 'C:\Media\Karaoke-Demo-New\master.mp4' 'C:\Media\Karaoke-Demo-New\replacement.wav' 'C:\Media\Karaoke-Demo-New\audio-variant.mp4'
python -m unittest discover -s tests -p test_karaoke.py -v
```

The fixture refuses a nonempty destination and contains no real song, downloaded
animation or personal channel data. CI covers these synthetic media operations;
models and browser publication require separate local validation.
