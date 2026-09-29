# Review remediation map

PR scope: actionable issues #1–#20 and tracker #21. A changed code path or exit code alone is not completion evidence. The matrix below identifies the implementation and corresponding acceptance tests; current exact-head CI and workstation evidence belong in the PR, not a stale hard-coded green badge.

| Issue | Remediation | Evidence |
|---|---|---|
| #1 BOM JSON | Shared UTF-8-SIG readers and no-BOM writers | Contract BOM test; actual PS5.1/7 Unicode-to-Python tests |
| #2 atomic render | Unique sibling, decode/QA gate, OS output lock, aliases, replace policy | Body/rename/encode/QA/cancel preservation tests; source hashes |
| #3 retry lifecycle | Durable reservation/stage/attempt/error state, bounded backoff/quarantine, clone reuse | Failure/quarantine, interrupted-copy, repeat-ingest tests |
| #4 resume provenance | Recorded clone selection, full-hash evidence, explicit unverified status, preserved history/read-only clone | Missing-original, legacy ambiguity, mismatch, wrapper resume tests |
| #5 short narration | Full-duration bed with padding/trimming | Decoded late music/SFX energy and all-short/long audio cases |
| #6 source ranges | Selected-stream bounds, timestamp precision tolerance, exact per-cut/final frames | EOF/overrun preflight, real frame-count QA, failure preservation |
| #7 registry concurrency | SQLite unique reservation/transactions and OS source/job locks | Independent concurrent same/different-source processes; lock and migration tests |
| #8 Windows command budget | External graphs, bounded per-cut inputs, UTF-16 serialized command checks | 240-cut long-Unicode-path render on Linux/Windows; command-budget unit test |
| #9 fractional FPS | Rational rates and one-time frame-grid quantization | 30000/1001, 24000/1001, 29.97, 23.976 real output probes |
| #10 near-EOF sampling | Precise invariant seeks, observed timestamps, fresh owned output runs, fallback verification | Short/one-frame/stale-output tests; PS comma-decimal tests |
| #11 TTS completion | STOP-only, intentional audio-part selection, MIME/base64/PCM/WAV validation, atomic WAV+receipt | Mocked malformed/truncated/finish-reason/multiple-part/provenance tests; no provider calls |
| #12 schema/preflight | Exported runtime schema, structured modes/errors, generated examples, nonoverwriting conversion | Schema equality/bad-value tests, real preflight, dry-run/no-write and conversion tests |
| #13 tests/CI | Hosted Linux/Windows/Python matrix with real FFmpeg, PS5.1/7 contracts and provider mocks | Required suite and retained CI environment/result logs |
| #14 operations/doctor | Tool/version/filter/config/storage readiness, scoped task lifecycle, captured paths, logs/health | Doctor and watcher-health tests; real isolated Windows scheduler acceptance |
| #15 docs/privacy | README, operations/API/timeline/testing guides, changelog, contribution policy, narrow allowlist, maintainer-selected MIT license | CLI/example walkthroughs, schema equality, staged-file privacy audit; maintainer authorized MIT on 2026-09-29 |
| #16 typed controls | Stable job JSON controls, revisions/history, split/trim/reorder/ripple guards/undo, bounded previews | CLI lifecycle, revision-conflict/undo, frame-grid preview tests |
| #17 footage index | Source/settings-keyed local SQLite evidence, observed samples/shots/words, bounded queries/stale detection | Known-shot/text/time/pagination/cache/invalidation tests |
| #18 audio capabilities | Per-clip stream/mute/gain, optional narration, delivery-quality resampling, ducking, measured normalization | Selected-stream and all audio-mode tests; decoded ducking/loudness measurements |
| #19 captions/graphics | Audible cut-aware word retiming; sidecar/mux/burn; file-backed typed Unicode titles | Cue selection/reorder/mute tests, real subtitle streams/burn and title pixels |
| #20 QA/cache boundary | Immutable receipts, opt-in gates, verified bounded cut cache, explicit JSON-only interchange | Decode/frame/duration/audio gates, cached-vs-uncached hashes, invalidation, cleanup/budget tests |
| #21 tracker | Acceptance mapping and exact-head evidence rather than premature issue closure | This map, CI, workstation results, and PR review |

Known boundaries are deliberate, documented failures rather than silent fallback: ambiguous legacy cuts/clones, unmeasurable loudness, unsupported output formats/filters, too many simultaneous external tracks, stale edit revisions, and ripple edits crossing external events/narration require an explicit operator decision. Optional live provider/model/GPU availability is not tested by an offline suite. No merge, server deployment, automatic paid request, or guessed license is implied by the PR.
