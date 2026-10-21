# Minecraft Shorts: capture, revisions, loops and upload

Reviewed 2026-10-21 after the Skydive Tower Short. This records observed failures,
creator preferences and reusable production decisions. It is not an audience
performance study or a claim that the shared pipeline implements every check.
Keep footage, world snapshots, prompts, upload receipts and credentials in the
private job. Read this with the [production workflow](PRODUCTION_LESSONS.md),
[editorial guide](EDITORIAL_GUIDE.md) and [canonical timeline contract](WORKSPACE.md).

## 1. Make the premise and picture agree

| Creator correction | Reusable decision |
| --- | --- |
| A roughly two-kilometre tower did not justify calling it a space elevator. | Name the structure for the experience actually shown. A skydive tower is a credible premise without an unsupported claim of reaching space. Update titles, narration, descriptions and artwork together when the premise changes. |
| The video should advertise the mod indirectly. | Make the build, ascent and flight the story. Use a brief brand payoff near the end rather than making every label a mod advertisement. |
| The repeated vanilla-height comparison and generic labels felt tired. | Use scene-specific language: lift departure, summit, equipment, flight route and approach. Keep a familiar benchmark only when it adds necessary context. |
| “Wings armed” played over a tower view. | Show the equipped player before the relevant word begins, and keep the equipment visible for the complete line. A nearby shot of the same location is not sufficient visual support. |
| The jump read as an uncontrolled fall, and landing beside the base made the route implausible. | Establish the equipment and intended flight, deploy wings visibly early, travel a meaningful distance and show a controlled approach to a surveyed landing area. Keep locations and movement consistent across cuts. |
| The closing invitation to “go again” felt forced. | Use a concise ending that fits the subject and creator's tone. A short brand line can fit this kind of showcase; do not apply that ending to every future video. |

For portrait framing, start with short text slightly above centre, but place it
around the subject in each shot. In an equipment close-up, move the panel above
the player instead of covering the wings. Review the actual composed frame at
phone size. Attractive generated lettering still needs spelling, transparency,
contrast and small-size readability checks. Reuse approved artwork and logos.

For an extreme-height build, capture a complete establishing view, a ground-up
reveal, mechanism and rider views, an equipment close-up, and distinct exterior
and player-POV flight angles. Check the whole frame for clipped neighbouring
structures. Full height and broad terrain must be visible in delivered footage,
not merely configured in a render-distance setting.

## 2. Verify the native scene before recording the batch

### Distant terrain and shaders

- Use the correct filming world and retain its terrain cache. A large configured
  Distant Horizons radius does not establish that the required LOD records exist.
  Inspect the requested detail levels along the camera route, not just the total
  database row count or whether existing records contain populated columns.
- In this production, missing requested LOD records caused rectangular terrain
  gaps. Filling missing records through native DH parent downsampling helped;
  that does not recover fine detail which the source data never contained. Avoid
  inventing terrain or treating a coarse vista as full-resolution chunk coverage.
- A frozen replay can move its export camera without advancing world ticks.
  The renderer must still update the distant-terrain camera/detail selection on
  the output-frame clock. Test a moving export, not only a stationary screenshot.
- Qualify terrain with the intended shader, output dimensions, camera heights
  and route. Review native chunks and distant terrain together near transitions,
  water, the coast and landing. Fixes for a high shot may fail near the ground.
- Cloud, reflection, frustum and overdraw adjustments are diagnostics, not a
  universal preset. Revert unsuccessful experiments and record the settings that
  actually produced accepted footage. Do not disable culling globally to conceal
  an unproven cause.
- Replay seek/loading was more reliable when the camera was staged with shaders
  and DH disabled, then both were enabled before capture. Treat this as a tested
  loading workaround, not proof that shader initialization stalls are fixed.
- Discard sufficient pre-roll after framebuffer or scene changes, then inspect
  the first frames actually selected by the edit. Pre-roll duration alone is not
  an acceptance test.

Prove the requested shader and terrain in the final framebuffer. A successful
API response, installed mod or enabled setting is not visual evidence.

### Motion, visibility and compatibility

Use the [replay timing guidance](PRODUCTION_LESSONS.md#smooth-offline-replay-footage)
to distinguish irregular recorded updates from slow export and slow playback.
Verify output-frame interpolation for camera and actor movement, discrete pose
changes, equipped items and actor visibility across section boundaries. Correct
frame rate alone does not establish smooth motion.

For a moving elevator or contraption, first verify actual boarding, travel and
stopping in the world. Keep rider, seat and cabin tracks on the same output
clock with consistent offsets, then inspect both exterior and rider POV takes.
A moving camera or player alone is not proof of a functioning mechanism.

Authored cinematic movement in a recorded world can produce a coherent montage,
but it does not prove real-time gameplay physics or performance. Preserve the
original replay and timing provenance. For gameplay proof, record the action
and retain its authoritative timing instead of silently substituting a cinematic
reconstruction.

When a mod-side defect blocks filming, fix the owning code and exercise the
affected runtime. This production exposed repeated skylight opacity reads,
global POI traversal during long routes, and a missing sparse-POI index entry
after reload. Reusable engineering checks are bounded per-solve work,
column-local sparse lifecycle operations, and flush/evict/reload regression
coverage on every affected port. Keep build, renderer, live-gameplay and native
capture evidence distinct. Record a retry honestly rather than claiming its
initial failure was diagnosed just because it later passed.

### Bounded recovery and cleanup

Use an owned filming profile with bounded memory and CPU use. Preserve the
settings it changes, keep the user's other sessions separate, and restore those
settings after capture. Close only owned clients, servers and launchers; keep
tokens and launcher account files out of logs and public Git.

A request timeout may occur after a replay open or seek has completed. Inspect
the current replay, source time, loading state and job status before retrying or
restarting. Resume completed work when its identity matches. Keep recovery
attempts bounded, and do not let a stale launcher instance turn repeated restarts
into another long debugging loop.

## 3. Check the actor, camera and sightline against the recorded world

The apparent jump through a window was not caught by a player-only clearance
check. The player started outside the glass, but the camera started inside and
crossed it, making the action read incorrectly. Earlier checks against the live
server also did not establish clearance in an older recorded scene.

Before accepting an obstacle crossing:

1. Identify the exact replay and source timestamp. Verify the scene is loaded;
   an empty or unloaded block sample cannot establish a clear route. Bind the
   geometry snapshot and path to their identities in private receipts.
2. Check the swept player bounds, including the relevant standing and elytra
   poses, through the whole action. Account for the actual collision shapes or
   use documented conservative bounds.
3. Check camera clearance and its near plane, and the camera-to-player sightline.
   A clear actor route can still yield a through-wall or obstructed shot.
4. Include the visible window, balcony, rail and nearby supports. If only that
   region is checked, state that scope; do not call it a whole-flight validator.
5. Keep the rejected path as a regression case: the old shot must fail and the
   replacement must pass. Invalidate the check when its path, scene or media
   changes. Use exported camera traces to verify the rendered path; establish
   eye-coordinate and timing conventions rather than assuming a fixed offset.
6. Inspect a cheap native probe, then the full-resolution take and final edited
   context. Geometry checks cannot prove that a jump looks plausible to a viewer.

The accepted replacement kept the camera outside the glass, showed the window
behind the player and made the balcony hop readable. A job-specific checker
enforced these checks; there is no general shared-pipeline collision gate yet.

## 4. Make small revisions without filming everything again

- Keep one canonical timeline with stable scene IDs, source ranges, narration
  and overlay anchors. Previous masters are history; derived render plans must
  be traceable to the current timeline rather than becoming competing edits.
- Record short replaceable takes with handles. Replace a defective launch while
  retaining approved lift, equipment and long-flight footage. Preserve the old
  source and approved master until the replacement passes review.
- Reuse already-composed ranges only when their picture, graphics and relative
  timing are unchanged. Mute their baked audio when rebuilding the current mix,
  and do not apply their overlays again. Record source hashes and range mappings.
- Exact stream copy can use byte/stream identity. A lossy re-encode needs aligned
  decoded-picture comparisons with a justified tolerance, not a byte-equality
  assertion. Review the changed range with context on both sides.
- Freeze inputs before rendering. Editing the canonical timeline during export
  correctly triggered the source-changed guard and wasted the first render.
  Review changed frames cheaply, settle the edit, then start the master.
- Reusing footage saves filming work but does not guarantee a fast export.
  Account for lossless intermediate preparation, decode validation, composition,
  audio analysis and final encoding. Profile the actual bottleneck before
  promising speedups or rebuilding unaffected work.

Keep complete narration takes at native speed. When trimming an opening, retime
the title, speech, other overlays, later scene anchors and ducking together.
Resolve speech overlap using suitable visual handles or new placements rather
than clipping words or silently accelerating a take.

## 5. Treat the loop as part of the edit

If the opening's first few seconds are unusable, remove those frames from every
reference, including an outro made by reversing the opening. Choose a clean
handle, rebuild the return from it and match the actual encoded first and last
frames. Do not let the closing logo linger into the next opening title.

Rebuild music for the new duration from continuous source material. A picture
trim must not cut the same samples out of a precomposed song bed. A cyclic
crossfade and a quiet stereo boundary worked here; they are not universal music
settings. Preserve musical phase, avoid a fade to silence at the loop, and
check the encoded AAC boundary, including padding and duration handling.

Review the final mixed narration as well as the isolated takes. ASR can check
that all intended lines are present, a rejected line is absent, and equipment
words align with the equipped-player shot. It cannot establish natural delivery
or replace listening. Full decode, frame count, loudness and boundary checks
supplement visual and audio review rather than approving the story themselves.

## 6. Upload the approved artifact and assess disclosure deliberately

Verify the approved master hash, channel identity and existing upload receipts
before transfer. Save the new video ID as soon as it exists so a retry does not
create a duplicate. If saved API authorization has expired, use the signed-in
Studio workflow when available; do not repeatedly retry a revoked token.

Save privately first unless the user explicitly requests public publication.
Check the saved title, description, actual source filename, thumbnail, video
language, audience setting, visibility and HD processing. Do not inherit an
unrelated default language. Link a relevant existing showcase as the related
video when it supports the Short. Initial platform checks do not guarantee
against later claims or restrictions. Upload completion and public publication
are separate results.

Creator preference: **do not automatically label a video as AI-generated merely
because it uses AI-assisted narration, title artwork or production help.** Do not
automatically describe the whole video as AI-made for those reasons either.
Evaluate the actual content against the platform's current disclosure criteria;
the proportion of AI-generated content alone is not the decision rule.

[YouTube's disclosure guidance](https://support.google.com/youtube/answer/14328491?hl=en),
checked 2026-10-21, distinguishes realistic meaningful alteration from minor or
non-realistic assistance. Gameplay and title/thumbnail assistance are examples
that do not by themselves require disclosure; realistic impersonation, fabricated
real-world scenes and music have additional criteria. Assess narration and music
individually rather than treating all synthetic voices alike or declaring a
blanket exemption. Recheck the live form and guidance at upload time.

## Before the next master

- Does the title promise only what the build and footage demonstrate?
- Is the intended terrain and shader visible throughout the selected footage?
- Do recorded-scene actor, camera and sightline checks reject the known bad shot?
- Does each equipment/status line show the relevant action or item, unobscured?
- Can the revision reuse verified takes and composed ranges?
- Are the canonical edit and its inputs frozen before export?
- Are all voice takes complete, with labels and ducking on the current clock?
- Are faulty opening frames also excluded from the loop return?
- Do the encoded picture and music join cleanly at the playback boundary?
- Is the exact approved artifact uploaded to the correct channel, with disclosure
  assessed from the content and current criteria rather than an automatic AI flag?
