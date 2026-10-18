# Browser editing workspace

Every video uses the same HTML, CSS, JavaScript and Python server in
`scripts/pipeline/web/` and `scripts/pipeline/workspace.py`. Never copy these files
into a job. A video's private `project.json` supplies its title, scenes, storyboard,
script and asset references. No project-specific media or narration is bundled.

## Create and open a workspace

Start with a valid pipeline timeline. The destination must be a **new directory**;
initialization refuses to overwrite an existing workspace.

```powershell
python scripts/pipeline.py workspace-init 'C:\Media\Episode\timeline.json' 'C:\Media\Episode\review' --title 'My episode' --script 'C:\Media\Episode\script.txt'
python scripts/workspace.py 'C:\Media\Episode\review' --port 8766
```

Open `http://127.0.0.1:8766/`. Python 3.10–3.13 and the repository's core
requirements are sufficient to start the server. FFmpeg/FFprobe are needed to build
previews. No model/provider request or full-video render occurs on startup.

On Windows, the shared launcher starts a hidden server and opens the browser:

```powershell
.\scripts\Open-Workspace.ps1 -Project 'C:\Media\Episode\review' -Port 8766
```

`-NoBrowser` starts/checks the server without opening a browser. The launcher honors
`PIPELINE_PYTHON`, then the repository virtual environment, then PATH. It checks the
workspace identity before reusing an existing server. Choose another port for a
different video. Logs and a PID file are written beside `project.json`; stopping
that specific server process preserves media and previews. For foreground use,
Ctrl+C shuts down the server after any active preview finishes. Restart after
editing the manifest. The current script file is read fresh whenever Full script
is opened or its version is selected.

## Optional inputs

- `--master PATH`: play an existing assembled cut. Without it, the UI reviews
  individual source clips and their selected ranges. Source review does not
  compose overlays, narration, music, zoom or output framing; Build preview checks
  those through the actual timeline renderer. Browser codec support varies.
- `--narration PATH`: a UTF-8 JSON array containing one narration string per
  timeline clip. These strings populate the scene sidebar and full Cut narration.
  Without them, scene narration is empty; the complete script file is independent.
- `--script PATH`: a UTF-8 text file (BOM accepted), shown completely, including
  any directions/notes, without parsing a particular project's chapter convention.
  Copy/download preserve the text. Without it, Full script shows cut narration.
- `--media-root DIRECTORY`: the explicit directory containing the timeline,
  workspace and every referenced asset/script. Defaults to the timeline's parent.
  Use a common project directory if assets are in sibling folders.

The initializer uses normalized frame-grid clip lengths and source offsets. It
does not transcribe footage, infer narration, extract arbitrary scripts, generate a
storyboard, or change the timeline. Stills are displayed as images in source review.

## Manifest format

The contract is `schemas/workspace-v1.schema.json`, exported from
`WORKSPACE_SCHEMA` in `scripts/pipeline/workspace.py`. Unknown properties, invalid
media references, nonfinite values and inconsistent scene ranges fail at startup.
Paths resolve relative to the manifest, or may be absolute. Each must resolve to a
file inside `media_root`; the manifest itself must also be inside that directory.
Only explicitly registered media IDs are exposed at `/media/ID`.

```json
{
  "version": 1,
  "title": "Example episode",
  "subtitle": "Review before recording",
  "media_root": "..",
  "timeline": "../timeline.json",
  "script": "../script.txt",
  "master": null,
  "duration": 4,
  "assets": {"opening": "../opening.mp4"},
  "scenes": [{
    "id": "opening", "title": "The opening", "start": 0, "duration": 4,
    "text": "Opening narration.", "media": "/media/opening", "media_in": 1,
    "media_type": "video"
  }],
  "storyboard": [{
    "id": "chapter-1", "title": "A new opening", "start": 0, "duration": 5,
    "text": "Draft words.", "media": null, "media_in": 0
  }]
}
```

Cut scenes must be sequential, start at zero and cover `duration`. Storyboard
chapters are independent visual references: `media_in` selects their source
offset, and their duration bounds playback. Their narration status is not inferred.
`media_type` may be `video` (default) or `image`. A null scene media reference shows
an explicit empty visual state. Omit `storyboard` or supply `[]` to hide that tab.
Omit `timeline` for playback/script review without rendering controls. `master`
must be null or an asset ID reference. If supplied, it is the assembled cut and
scene timestamps seek within it.

Change scene titles/text and add storyboard entries in the manifest as needed.
Keep revisions of scripts and media private. For a changed timeline, generate a
new workspace and carry over relevant editorial metadata; a duration mismatch
fails rather than silently seeking against stale timings.

## Local service and previews

The server binds only to IPv4 loopback. Host/Origin checks reject other origins;
static routes and media IDs are allowlisted, and HTML never interprets project
strings as markup. Byte-range and HEAD requests support video seeking. Responses
are not cached. Script, timeline, manifest and directory paths have no generic
file-serving route. Preview output stays in the workspace's `previews` directory.

One preview is queued/rendered at a time, with a 30-second range limit and a
180-second render timeout. A session accepts up to 100 previews; restart for a
new session. Restart loses the session's task URLs but preserves files. Failed
previews leave previous deliverables intact. The UI never starts full exports.
This is a local review tool, without network authentication or public hosting.

## Migrating older copied editors

Keep the existing private manifest/media, add `version: 1` and `media_root`, then
validate it with `python scripts/workspace.py PATH --describe`. Point its launcher
at the shared `scripts/Open-Workspace.ps1`. After successful playback/script/preview
checks, remove the copied `index.html`, `app.js`, `style.css` and project-local
server. Preserve timelines, source files, narration, previews and editorial data.

Project-specific footage preparation may remain local, but it must produce this
manifest format and use the shared UI. Future UI fixes then apply to every project
when it uses the updated pipeline checkout.
