# Operations and recovery

## Ownership and disk use

Only work inside a configured checkout/workspace. The original source is opened read-only; ingest allocates a stable job transaction before copying. The clone lives under `jobs/JOB_ID/source`, is full-SHA-256 verified, and is made read-only. No size threshold changes a sampled comparison into a false full-verification claim. An interrupted `.copying` file is owned by that job and is replaced on retry; a mismatching completed clone is retained for investigation rather than silently overwritten.

Keep free space for the source clone, analysis derivatives/samples, active lossless render cuts, the staged deliverable, and retained QA history. The default 1 GiB cache budget is **not** a cap on active workspace disk usage. Doctor's 256 MiB free-space floor is an environment sanity check, not a guarantee that a large job will fit. Disk-full and permission failures must remain failed jobs without READY and without replacing a deliverable.

The SQLite registry uses transactions and a busy timeout. Per-source/per-job and output/cache operations use OS-held advisory locks. A crashed process releases ownership automatically; retained lock files are not evidence of a live owner and must not be deleted to force ownership. Independent sources can be prepared concurrently; the same source identity owns one workspace. Different source content/mtime identities are new jobs, not invisible mutation of an old job.

## Retry and cancellation

Automatic attempts default to three, with exponential retry delay starting at 30 seconds and capped at one hour. Configure `max_attempts` and `retry_base_seconds` explicitly. Failed analysis reuses the verified clone. Repeated failure reaches quarantine, preventing unbounded duplicate copies on every watcher poll.

Inspect `job-status ID` before taking action. Use `retry ID` to deliberately reset the attempt budget, `cancel ID` to stop active work, and `quarantine ID` to hold a stopped job. Cancellation checks source-copy blocks, render hashes, and owned FFmpeg child execution. Only the subprocess created by that operation is terminated; unrelated processes are not targeted. A fully published output is a completed transaction; a later cancellation does not roll it back.

Power loss after clone publication but before analysis completion is recoverable with the same registry row/clone. Power loss after a media output was atomically published but before a caller displayed success can leave a valid new output; use its receipt/hash rather than assuming failure from a disconnected terminal. Every stage must distinguish prepared input from a rendered/QA-approved deliverable.

## Resume and migration

```powershell
.\scripts\MediaPipeline.ps1 -Action Resume -JobPath 'C:\Pipeline\jobs\JOB_ID'
.\scripts\MediaPipeline.ps1 -Action Resume -JobPath 'C:\Pipeline\jobs\JOB_ID' -SourcePath 'C:\Media\Original.mkv'
```

Resume uses the recorded clone path. A legacy manifest without that field must have exactly one candidate source file; ambiguity fails. It preserves original path, creation time, hashes, notes, existing timeline work, and verification history. A recorded full hash can verify a clone even when the original is unavailable. With neither original nor trustworthy full hash, preparation may complete but verification is explicitly `unverified`; it is never promoted merely because the clone exists.

An explicitly supplied original must match. When a previously verified original pathname has since been reused for different content, historical clone provenance remains valid and the current original is recorded as changed rather than overwriting the original provenance. Hash mismatch, a missing recorded clone, or a clone/original alias prevents successful resume. Read-only protection is restored on the selected clone.

On first SQLite initialization, `state/processed.json` is imported without rewriting/deleting the legacy registry. Unrecognized or malformed data is not treated as an empty registry. Existing cloned media and editorial work are not migrated by destructive rename. A missing prepared workspace/artifact is marked stale instead of allocating a replacement behind the user's back. Keep the legacy registry and a backup until migration/recovery has been verified.

## Watcher management

`Install-Watcher.ps1` provides `Install`, `Start`, `Status`, `Stop`, and `Remove`; legacy `-Remove` remains accepted. Default task names contain a hash of the checkout root. Installation captures absolute Python, FFmpeg, FFprobe, CLI, root, and config paths in local state, so an interactive shell's PATH is not silently required after login. A task with unproven ownership is never overwritten just because its name matches.

The scheduled task runs in the installing user's interactive session at logon; it is not configured as SYSTEM and does not store a password. Installation checks doctor/setup before registration. `-StartNow` starts immediately. Task removal preserves all jobs and configuration. The older unscoped `CodexVideoMediaInbox` task is not removed automatically: inspect it, stop/unregister it explicitly in Task Scheduler when deliberately migrating, then install the scoped watcher. Do not run old and new watchers against the same jobs directory.

`Stop` writes a cooperative stop request. `Status` reports scheduler state/result and the durable watcher-health record; wait for `stopped`/non-running state before assuming completion. Forced task removal may interrupt work, which is why copy/retry state is durable. At most one foreground watcher owns a workspace. Starting a second watcher fails with `busy` instead of racing registry snapshots.

Logs rotate at 1 MiB with three backups. `state/watcher-health.json` records heartbeat, stage, job, most recent successful preparation, and error. A long analysis stage can have an older watcher heartbeat while its job record continues progressing; inspect both rather than declaring the job dead from directory age. Metadata publication retries short Windows reader-sharing conflicts for at most three seconds, then fails without exposing partial JSON. This prevents a concurrent PowerShell status read from crashing the writer; permanently locked/unwritable files still require operator recovery. Core logs do not include provider credentials or raw narration scripts. A task that fails before Python can initialize should be diagnosed through `Status`/Task Scheduler's last result and `doctor`, not by assuming an absent health file means idle success.

## Optional tools and privacy

Core installation is `requirements.txt`; provider/transcription packages are in `requirements-optional.txt`. Whisper model downloads require `--allow-download`; supplying a local model directory avoids downloads. Provider requests require `--allow-paid`; each invocation is one explicit request with a configurable text-size ceiling. There is no automatic retry loop that can multiply provider spending.

Transcription publishes an immutable bundle and atomically updates `analysis/transcript.json` as its commit pointer. Use its `srt` and `text_file` paths instead of guessing legacy flat output names. TTS publishes only completed, format-validated WAV audio and an immutable provenance receipt recording model, voice, hashes, size, and completion, not the raw script/key. Provider availability, quotas, voice consent/rights, and media/font licensing remain the operator's responsibility.

Keep job state, thumbnails, captions, transcripts, generated audio, reports, and logs out of public Git. They can contain private source paths, dialogue, or editorial intent even without the original recording. Never use cleanup commands against a broad personal media directory; the pipeline's own cleanup is limited to owned temporary/cache/sample artifacts.
