# Browser editing workspace

Each workspace has **one canonical timeline**. Its clips define scene order,
source ranges, narration text and production status. The browser, full-script
panel, range renderer and final renderer all use that edit. Do not maintain an
"existing cut" and a separate "revised storyboard" as competing current edits.
Unused takes belong in the source library; previous exports and revision
snapshots are history, not another active timeline.

The shared UI and server live in `scripts/pipeline/web/` and
`scripts/pipeline/workspace.py`. Never copy them into private jobs.

## Create and open

```powershell
python scripts/pipeline.py workspace-init 'C:\Media\Episode\timeline.json' 'C:\Media\Episode\review' --title 'My episode'
python scripts/workspace.py 'C:\Media\Episode\review' --port 8766
# Or launch a hidden server and open the browser on Windows:
.\scripts\Open-Workspace.ps1 -Project 'C:\Media\Episode\review' -Port 8766
```

Initialization requires a valid pipeline timeline and a new workspace directory.
It does not render a complete video or generate narration. The manifest and all
referenced inputs must be inside `media_root`, which defaults to the timeline's
parent; use `--media-root` for assets in sibling directories. Python 3.10–3.13
and the core requirements start the server; FFmpeg/FFprobe build previews and
validate media during edits.

`--narration PATH` explicitly imports a UTF-8 JSON array with one string per
clip into that timeline. `--script PATH` imports a single-clip script only;
multi-scene prose requires an explicit per-clip mapping. These are one-time
imports, not separately maintained script files. Unknown mappings fail rather
than silently placing a newer script alongside an older cut.

## Edit and preview

- Select a scene to edit its title and narration. **Save script** persists to
  the canonical timeline using its expected revision. Unsaved changes remain
  in the editor until saved or discarded.
- Use source in/duration to apply an equal-length slip or a shortening ripple
  trim. The existing pipeline editor rejects unsupported extensions and edits
  crossing audio/graphic events rather than silently breaking synchronization.
- Move scenes earlier/later when there are no independent timed layers. For
  timelines with timed audio, captions or graphics, reposition their anchors
  explicitly through the timeline editor first. These buttons do not pretend
  to implement arbitrary multitrack ripple editing.
- **Undo last save** restores the revision before that save as a new revision.
  Older snapshots remain private history. Concurrent stale writes return a
  conflict instead of overwriting newer work.
- The viewer follows the selected timeline sources, including trims and image
  durations, and can advance through scenes without a full export. This quick
  source playback does not compose overlays, narration, music, zoom or output
  framing. **Build preview** renders up to 30 seconds of the same timeline with
  its actual composition. These are two playback fidelities of one edit.
- **Full script**, copy, download and `/api/script` derive narration from clips
  in timeline order. There is no alternate script selector.

Mark unfinished visuals `draft` and unrecorded narration `pending`. The UI shows
those states on scene cards and the narration track. They are production notes,
not a claim that a recording was verified automatically. Pending scenes may be
previewed; a successful preview does not mean that narration or animation is done.
Use labeled placeholder images for missing visuals, not silently reused shots
from a previous script. Choose provisional durations explicitly; fit the final
edit to measured complete narration when it exists.

Changing narration text marks it pending. If a clip explicitly marked its
embedded narration as recorded, its audio is muted. An existing global voiceover
is detached and all affected scene narration is marked pending; undo retains
the prior configuration. This avoids playing old spoken words under new text.
Recorded-status labels alone do not attach or generate audio.

The server rereads the timeline for project, script and preview requests. The
browser checks for saved external changes every five seconds when it has no
unsaved script changes. No manifest regeneration or server restart is needed
for normal edits. Restart after changing the project binding or server code.

## Manifest v2 and scene fields

`schemas/workspace-v2.schema.json` is exported from `WORKSPACE_SCHEMA`.
There are no independent `scenes`, `storyboard`, `script`, `duration`, `assets`
or `master` fields in the manifest:

```json
{
  "version": 2,
  "title": "Example episode",
  "media_root": "..",
  "timeline": "../timeline.json"
}
```

Store editorial data on each clip in the existing timeline v1 schema:

```json
{
  "id": "opening",
  "source": "opening.mp4",
  "in": 0,
  "duration": 8,
  "audio": {"mode": "mute"},
  "editorial": {
    "title": "Where do I start?",
    "text": "The opening narration.",
    "visual_status": "draft",
    "narration_status": "pending",
    "notes": "New animation and narration still needed."
  }
}
```

`visual_status` is `draft` or `ready`; `narration_status` is `pending`, `recorded`
or `none`. Legacy timeline clips without editorial fields remain usable. Source
ranges and total duration derive from the normalized rational frame grid, not
duplicated scene timings in a workspace manifest.

## Exports and preview validity

`--master PATH` may bind a previously verified export of the exact input
timeline. This is a caller-supplied association, not an automated check that
the spoken words match the script. The manifest stores it under `render` with
the normalized timeline's SHA-256. It is only offered for playback while that
hash matches. Any timeline change, even a text-only change or an external edit
without a revision increment, makes that export stale. It stays on disk and
cannot silently override current sources. Editing sources in place is still
discouraged: use immutable/versioned media and update their timeline references.
Bound export playback URLs include the timeline fingerprint. Rebinding an export
at the same filename after an edit therefore reloads the video element instead
of retaining frames already buffered from the previous edit. The server's
no-store response alone does not clear an existing video buffer.

A range preview snapshots the exact requested timeline before queuing, records
its revision/hash and renders that snapshot. Saving another edit during a render
cannot change the queued composition. The browser refuses to activate the result
as the current preview if the timeline has changed. Snapshot JSON, previews and
history remain private job data.

## Local service

The server binds to IPv4 loopback. Host/Origin checks reject other origins;
static routes and media IDs are allowlisted. Project strings are never rendered
as HTML. Byte-range and HEAD requests support video seeking. Paths have no
generic file-serving route. Inputs and restored revisions are checked against
the workspace root before a workspace edit is committed.

`POST /api/edit` accepts `expected_revision` and a supported timeline `operation`
(`editorial`, `trim`, `reorder`, `undo`). `POST /api/preview` accepts `start`, `end`
and the current `timeline_sha256`. One preview is queued/rendered at a time,
with a 30-second range limit, 180-second timeout and 100-preview session limit.
The UI never starts complete exports. This local tool has no network
authentication or public hosting.

The Windows launcher uses `PIPELINE_PYTHON`, then the repository environment,
then PATH. It checks the workspace identity before reusing a server; it also
checks the API version so outdated server code requires a restart. `-NoBrowser`
does not open another tab. Logs and a PID file stay beside `project.json`.

## Migrate a v1 workspace

The v1 schema remains available as a historical format; the current server
rejects it with migration guidance. It does not guess which conflicting edit
should win.

1. Back up the private manifest and timeline outside the active workspace.
2. Choose the intended current edit. Translate its scenes into canonical clips,
   preserving source paths/ranges, scene narration and production notes. Use
   labeled images for missing visuals and validate source bounds. Preserve
   unused footage separately rather than appending it as accidental chapters.
3. Store each scene's text/status under `clips[].editorial`. Remove outdated
   narration/audio from the active timeline; keep the files in history.
4. Replace the manifest with v2 pointing to that timeline. Do not bind the old
   master as a current render. Keep prior exports as historical files.
5. Validate with `python scripts/workspace.py PATH --describe`, restart the
   owned server, and review the opening, script, scene navigation and a short
   composed preview. Remove copied UI/server code only after the shared UI works.

Project-specific preparation remains private and should update this canonical
timeline. It must not regenerate an older cut/storyboard pair over current work.
