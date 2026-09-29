# Testing and compatibility

## Required suite

```text
python -m pip install -r requirements.txt
python -m compileall -q scripts tests examples
python -m unittest discover -s tests -v
git diff --check
```

FFmpeg and FFprobe are mandatory. Tests generate deterministic colors/tones/stills and validate decoded video/audio, not just process exit. Use a writable temporary/work drive with at least 256 MiB available; long-media exercises need more. On Linux, `TMPDIR=/large/work/directory` selects a suitable test directory. Tests remove only their owned fixtures/workspaces and restore permissions on their own read-only clones during teardown.

Core CI is four hosted-runner combinations: Ubuntu 24.04 and Windows Server 2022, each with Python 3.10 and 3.13. Linux uses the distribution's FFmpeg 6.1 series; Windows downloads FFmpeg 7.1.1 with a pinned SHA-256. Windows also installs checksum-pinned PowerShell 7.5.3 and invokes Windows PowerShell 5.1. Version/dependency and test-result artifacts are retained seven days. Actions themselves are pinned by commit; permissions are read-only, credentials are not persisted, and no private/self-hosted runner or provider secret is required.

Manual acceptance also runs on Linux/Python 3.13.7/FFmpeg 7.1.1 and a real Windows workstation with Python 3.13.5, FFmpeg 7.1.1, Windows PowerShell 5.1, and PowerShell 7.5.3. The isolated interactive scheduled-task test is enabled with `PIPELINE_TEST_TASKS=1` on that workstation. Hosted service runners intentionally skip that one interactive-session test; this is not presented as a successful scheduler execution there. The other five Windows-specific tests are mandatory on Windows and fail if either shell is absent.

Direct dependencies are pinned in the requirements files. Core CI validates the resolved transitive set and records `pip freeze`; dependency refreshes must pass the same matrix. Optional SDK/model interfaces are mocked in deterministic tests. A successful mocked response is not evidence that a particular live model is available, that an API key works, or that a GPU/CUDA combination is compatible. No paid TTS request, transcription model download, or GPU benchmark is claimed by this suite. Runtime doctor reports installed optional packages separately from core readiness.

## Coverage

`test_contracts.py` covers UTF-8/BOM policy, schema equality and bad fields, rational-rate math, aliases, atomic-body/rename failure, Windows UTF-16 command budgets, real child cancellation, OS lock ownership/release, config validation, cancellation-versus-READY races, caption word bounds, and malformed/incomplete TTS responses.

`test_media.py` runs real FFmpeg for short/long/absent narration, late music/SFX, silent/source-only/music-only outputs, selected original audio streams, rational/decimal frame rates, source bounds, encode/QA/cancellation failure preservation, cached/uncached equality, 240 cuts with long Unicode input paths, nonmutating command inspection, near-EOF/one-frame sampling, two-pass loudness, ducking, title pixels, subtitle streams/cue timing, revision editing/undo, frame-grid previews, and footage shot/text/time/pagination/invalidation behavior.

`test_jobs.py` covers one-copy idempotence, prepared artifacts, failure/backoff/quarantine, verified-clone reuse, interrupted staging copies, concurrent same/different sources, full-hash resume without the original, explicit unverified legacy recovery, ambiguous clones, mismatch preservation, legacy registry import, audio-only preparation, JSON controls, watcher health, and doctor readiness.

`test_powershell.py` actually parses/runs every PowerShell entry point on both engines, writes non-ASCII JSON through each engine into Python, samples under a comma-decimal culture, and ingests/resumes through the wrappers. It also holds a real Windows file handle without delete-sharing and verifies that atomic JSON publication retries until the reader releases it. Its opt-in scheduler test creates a uniquely named task and synthetic inbox, verifies real preparation and health, requests stop, then unregisters only that test task. Failure cleanup preserves the workspace and removes the owned task.

`test_regression_edges.py` adds mocked local-only ASR and interrupted transcript publication, caption input validation/markup/muted narration, a real Git privacy allowlist check, nonzero source timestamps, variable-frame-rate normalization, longer-audio/video-bound separation, missing-clone readiness, and two-pass loudness command inspection.

## Extending coverage

`test_review_regressions.py` adds the review's change/fail/restore/rerender cache sequence with decoded red/green picture and 440/880 Hz audio checks, mutation-and-restoration during the real encoder call, legacy pathname reuse and duplicate historical jobs, and every-frame split/preview color equivalence for 24 fps, 2 fps, and VFR footage on a 30 fps timeline (including a non-grid source in). Only mutation timing is hooked; FFmpeg, hashes, SQLite, and publication are real.

Preserve failing-case tests when fixing bugs. An accepted source range must also produce the required decoded frames. A valid output file must still have the correct streams, audio duration, and late-track energy. A failed render must preserve both source hashes and the previous deliverable. A registry test must use independent processes when testing interprocess ownership; an in-memory mock cannot prove it.

Long simultaneous overlay/audio commands have an explicit precompose/shorter-path failure policy; the scalable-cut test does not claim unbounded simultaneous tracks or unbounded disk usage. Scene detection is tested against known luminance changes, not claimed as general video understanding. Preview timing is checked, but stateful compressor history and different preview encoding settings prevent a general bit-identity claim. No native editor interchange format is declared implemented.
