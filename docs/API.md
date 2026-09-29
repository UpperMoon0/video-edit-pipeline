# JSON CLI and editing API

Run `python scripts/pipeline.py --help` for the complete command list. Global `--root` and `--config` options precede the command. Relative config inbox paths resolve against that file; timeline assets resolve against their timeline. Output is one JSON envelope: `{"ok": true, "result": ...}` or `{"ok": false, "error": {"code", "field", "message", "hint"}}`. Persisted failed/quarantined/cancelled jobs are returned as structured `result` records with `ok: false`; their stable IDs remain usable. Errors may omit fields that do not apply.

Exit 0 means the requested operation completed successfully; exit 1 indicates validation, environment, media, or terminal-job failure; exit 130 indicates interruption. A dry validation success is not a render, transcript, or provider-success claim. The legacy `render_timeline.py` wrapper prints its render/validation result directly for compatibility.

## Job controls

```text
pipeline.py setup
pipeline.py doctor [--human]
pipeline.py discover
pipeline.py ingest SOURCE
pipeline.py resume JOB_DIRECTORY [--source ORIGINAL]
pipeline.py watch [--once]
pipeline.py jobs-list [--status STATE] [--limit N] [--offset N]
pipeline.py job-status JOB_ID_OR_PATH
pipeline.py latest-ready
pipeline.py retry JOB_ID_OR_PATH
pipeline.py cancel JOB_ID_OR_PATH
pipeline.py quarantine JOB_ID_OR_PATH
```

Job IDs are durable UUIDs, not sorted directory names. Records include the original identity, workspace, status, stage, attempt count, retry timestamp, cancellation request, error, preparation time, and update times. `latest-ready` uses durable successful preparation order and excludes missing/stale artifacts. List pagination is bounded; use the returned offset for the next page.

`retry` is explicit: it resets the bounded attempt budget and reuses a verified clone/workspace rather than allocating a second source copy. `cancel` cooperatively stops the owned operation, invalidates READY, and retains diagnostic state. `quarantine` prevents automatic retry; a running operation must be cancelled before manual quarantine. See [operations](OPERATIONS.md) for power-loss and legacy recovery.

## Timeline controls

```text
pipeline.py timeline-get TIMELINE
pipeline.py validate TIMELINE [--media]
pipeline.py edit TIMELINE --expected-revision N --operation OPERATION_JSON
pipeline.py preview TIMELINE --start SECONDS --end SECONDS [--output NEW_PREVIEW]
pipeline.py render TIMELINE [--job JOB_ID] [--no-cache]
pipeline.py convert-scaffold SCAFFOLD NEW_TIMELINE
```

`timeline-get` exposes normalized stable clip IDs and the current revision. Each edit checks that revision under an OS lock, validates the entire candidate timeline/media, saves an immutable prior revision, then atomically replaces the JSON. Conflicts fail with `stale_revision`; no change is silently rebased. Undo creates a **new** revision rather than reusing an old revision number.

Supported operation JSON:

```json
{"op": "split", "clip_id": "intro", "at": 1.5}
```
```json
{"op": "trim", "clip_id": "intro", "in": 0.5, "duration": 1.0, "ripple": true}
```
```json
{"op": "reorder", "clip_ids": ["detail", "intro"]}
```
```json
{"op": "ripple-delete", "clip_id": "detail"}
```
```json
{"op": "undo", "revision": 0}
```

Split time is local to the selected clip and is quantized to its frame grid. The left clip keeps its ID; the right gets a new ID. Equal-duration trim/slip edits preserve global timing. Duration-changing trims require `ripple: true` and may shorten, not extend, a clip. Reorder requires an exact permutation of all clip IDs; global overlay/music/title times remain explicit timeline times rather than implicitly following a clip.

Ripple deletion removes fully contained events and shifts events wholly after the deleted range. Events crossing the removed range, or an external narration track requiring editorial decisions, cause an actionable rejection instead of silently changing fades, words, or music. Split/reposition those events or remove/re-edit narration explicitly first. The only clip cannot be deleted into an empty render.

Previews select at most 30 seconds on the same rational frame grid, rebase selected clips and events, retain source offsets/fade phases, and cap width at 640 pixels with a fast H.264 preset. They never replace the final deliverable and do not use its cache. Empty caption ranges are omitted. Whole-program QA thresholds are not reused as range-specific silence/black thresholds. Stateful dynamics begin within the selected range; a preview is not promised to be bit-identical to a slice of the full program's compressor/loudness history.

`render --job` attaches progress/cancellation to a registered job and requires a timeline inside that workspace. A failed or cancelled delivery retains the prior video and records a failed job operation; explicit retry/resume restores preparation readiness. Standalone render remains available without registry mutation.

Scaffold conversion requires an unused destination and an unambiguous source. Nonempty legacy `cuts` have no defined machine schema and are not discarded or guessed; translate that editorial work explicitly. Existing `clips` timelines are already normalized by validation.

## Footage evidence

```text
pipeline.py sample SOURCE OUTPUT_DIRECTORY --interval 10 --start 0 --end 0 --columns 4 --rows 4 --width 320
pipeline.py index SOURCE --index LOCAL_INDEX.sqlite3 [--transcript TRANSCRIPT.json] [--samples index.json] [--threshold 0.3]
pipeline.py query --index LOCAL_INDEX.sqlite3 --text "phrase" --kind transcript --limit 20 --offset 0
pipeline.py query --index LOCAL_INDEX.sqlite3 --kind shot --start 30 --end 60
pipeline.py query --index LOCAL_INDEX.sqlite3 --kind sample --asset-id sha256:HASH
```

Sampling returns observed decoded-frame timestamps, actual requested/fallback seeks, frame paths, and contact-sheet references. Each run uses fresh files; an old frame cannot satisfy a failed seek. Invalid intervals/layout/ranges are rejected before mutating an existing index. Only a previously published run with the exact owned marker is eligible for replacement cleanup.

The SQLite footage index keys assets by full source SHA-256 and analysis settings/version. It records shot boundaries from FFmpeg scene-score evidence, sample references, transcript segments/words, and explicit no-audio/missing-transcript status. Reindexing an unchanged asset/settings set reuses its completed entry; changed media/settings invalidate it. Asset publication is transactional, so interrupted analysis can be rerun without losing completed entries. Incremental/resume granularity is **one asset**, not a partially analyzed frame stream.

Queries are bounded to 100 results per page and provide usable source ranges, original evidence, nearby observed samples, and shot/contact-sheet references. Source content is rechecked before returning indexed evidence. Changed/missing sources are reported as stale, not presented as current facts. Text search is case-folded literal transcript matching; it is not embedding search or an invented visual description. Scene score is a configurable heuristic, not a semantic promise that every editorial shot is detected. Original video decoding and word timing remain the authority.

## Interchange boundary

Timeline v1 JSON is the supported programmatic interchange format. No XML/EDL/OTIO exporter is claimed. A future adapter must explicitly map unsupported effects, mixed audio, captions, source paths, rational rates, and revisions rather than producing a superficially valid but lossy editor project. Provider/MCP/desktop integrations should call the typed CLI or its Python functions, not rewrite SQLite rows or bypass validation.
