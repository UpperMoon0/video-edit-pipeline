# Changelog

## 0.2.0 — review remediation

Review follow-up: bind cached cuts to verified private source snapshots; import historical jobs without claiming new recordings at reused pathnames or dropping duplicate history; normalize video frame selection before splitting and preview trimming. New real-media regressions cover all three failures. This supersedes the earlier completion claim pending fresh CI and review.

Replaces snapshot-based job bookkeeping with durable SQLite allocation, bounded retries, cancellation, quarantine, and OS-owned locks. Full-file clone verification and provenance-preserving resume keep original media untouched. Legacy JSON registry import retains the original file.

Adds a versioned timeline schema, structured validation and media preflight, rational frame timing, source-bound checks, bounded cut commands/cache, QA-gated atomic publication, full-duration audio, source stream selection, optional narration, ducking, and measured two-pass loudness normalization.

Adds precise sampled-frame evidence, typed JSON editing controls with revisions/history, bounded range previews, local footage indexing/search, cut-aware captions, sidecar/mux/burn delivery, and safe file-backed Unicode titles. TTS now validates completion and audio payloads; optional providers/models are no longer imported or downloaded by core startup.

Adds doctor diagnostics, per-checkout Windows watcher lifecycle operations, bounded logs and health records, synthetic examples, Linux/Windows CI, and operational/API/privacy documentation. Includes the maintainer-selected MIT license.

Footage index rebuilds now restore missing or empty generated thumbnails/contact sheets instead of returning a stale cache hit. Missing explicitly supplied sample evidence produces an actionable error without replacing the previous index.
