# Minecraft AI video: corrections to carry into the next production

Recorded 2026-10-19 from the creator's corrections during scripting, capture,
editing, packaging and private upload. This is a reusable editorial retrospective,
not an audience-performance study. Acceptance of an edit does not establish a
retention or CTR improvement. Detailed footage, scripts, research, credentials,
upload receipts and render evidence remain in the private job.

Read this alongside [the editorial guide](EDITORIAL_GUIDE.md),
[production workflow](PRODUCTION_LESSONS.md) and
[the one-timeline workspace contract](WORKSPACE.md).

## 1. Build a story for someone who has not watched it yet

| Creator correction | Working rule for the next video |
| --- | --- |
| “Then I made the test harder” did not give viewers a reason to care. | Lead packaging with the ambition, conflict or visible change that matters to a viewer. A test procedure is supporting material, unless the procedure itself is the attraction. |
| The opening needed the uncertainty of not knowing where to start. | Establish a relatable question, the goal and the first obstacle. A thought experiment can create curiosity before the technical explanation. Do not open with an academic summary of the conclusion. |
| The script sounded like a collection of AI-written punchlines. | Read adjacent paragraphs aloud as connected speech. Keep natural reasoning and transitions; remove repeated rhetorical flourishes, slogans and artificial cliffhangers. |
| Viewers needed to understand what changed between generations. | Explain each meaningful change as problem → approach → visible consequence. Keep core ideas such as learning from rewards, copying examples and training against a fixed opponent. Omit library names and architecture details that do not help explain the result. |
| The playable opening still contained older narration after the script changed. | Check the actual spoken opening in the composed preview against the canonical script before calling a revision ready. Updated prose alone is not an updated video. |
| The ending needed to acknowledge the gap to real PvP players. | Finish with the demonstrated achievement, its remaining limits and a concrete next challenge. Distinguish a future ambition from a capability already established. |
| A zombie-first description undersold the whole video; unexplained “V5” assumed prior knowledge. | Write title, thumbnail, description and chapter names for a first-time viewer. Cover the whole video's promise. Use “the latest bot” or explain a version label before relying on it. A first exercise should not stand in for the entire story. |

Before recording narration, make a cheap opening preview containing the proposed
hook, representative picture and voice. Review whether it creates a reason to
watch and leads naturally into the first experiment. This is an internal review
step, not a requirement to ask the creator to approve every routine decision.

## 2. Design an explanation, not a decorated slide

The creator repeatedly rejected visuals that looked finished but did not explain
the words. More animation or more generated sprites cannot fix an unclear idea.

| Rejected or corrected presentation | Better default |
| --- | --- |
| An isometric arena and abstract connections added little understanding. | Start with a readable 2D relationship, task map or interaction. Use 3D when spatial depth itself matters, and gameplay when demonstrating actual behavior. |
| Several headings plus generic episode branding and corner badges crowded the image. | Use one scene-specific title. Omit episode numbering, “thought experiment,” “illustration” and similar labels when they add no useful information. Retain qualifications that actually prevent a false inference. |
| Identical robot sprites were used for fighting, moving, defending and four “moments.” | Preserve character identity but use distinct poses and actions. For a history, show what changes across time and how that affects the next decision. Repeated avatars do not explain memory. |
| A human in diamond armor represented the AI. | Establish a consistent visual identity for each role. In this project a robot represented the AI; a human represented the later player challenge. That distinction is project-specific, not a requirement for every video. |
| The left zombie faced away from its target. | Check who each character faces throughout entrances, movement and mirrored layouts. Facing should communicate the interaction before a label is read. |
| Unexplained squares, generic icons and repeated flags stood for terrain or many scenarios. | Show recognizable obstacles, routes, goals and representative scenario categories. Include short labels where imagery alone is ambiguous. Explain what a count measures, such as “6 scenarios,” rather than showing a bare number. |
| “Attack ready” was ambiguous. | Use the precise viewer-facing concept, such as “attack cooldown ready.” Brief text should still identify the quantity or state correctly. |
| Clocks could be read as losses; batches were only called Set 1 and Set 2. | Pair the symbol with “Timeout: time limit reached.” Separate wins, losses and unfinished fights. Explain what distinguishes batches, and label a repeat batch as a repeat rather than inventing a new condition. |
| “Higher overall” and “worse here” had no understandable quantities. | Compare actual baseline and candidate values on the same labeled scale. Name the weak matchup. Identify an early rejected trial separately from the final model. |
| Fallback was an arrow pointing at a robot. | Show the decision, available alternatives and active controller-to-actor connection. Make the difference between selecting a behavior, training it and evaluating it visible. |
| Arrows disappeared behind bubbles or were covered by animated dots. | End connectors outside text boxes, leave arrowheads visible and remove pulses on short connectors. Remove the connector entirely if grouping or a highlight is clearer. |
| A bot barely moved along a route and slowed excessively near the end. | Animate progress by distance along the path. Fit a complete traversal and a brief arrival hold into the shot, with readable corners and no accidental loop reset. |
| One score slide remained while narration moved through several claims. | Map separate visual beats to test coverage, combined score, source of gains, regressions and limits. Reveal or animate quantities as they are discussed. |

For every visual beat, answer: **What should the viewer understand after seeing
this? What visible change communicates it?** If only the caption supplies the
answer, redesign the picture before rendering a polished animation.

Use generated transparent sprites when useful for distinct, consistent artwork.
Inspect real alpha, edge quality, action pose, orientation and small-size
readability. Do not add equipment or abilities the system has not demonstrated.
Generated promotional art is illustration; it must not masquerade as measured
gameplay evidence.

## 3. Capture a demonstration that actually tests the advertised behavior

- Verify the current mod/build and capture capabilities before assuming a tool
  is unavailable or downgrading the environment. Keep a documented fallback,
  but prefer the requested compatible replay setup when available.
- Inspect lighting and camera clearance in the final rendered image before a
  batch. A working replay is not proof of a bright, unobstructed shot.
- Plan genuinely different views: establishing geography, tracking, close
  exchange, participant POV, reverse and result. Cut between synchronized views
  of the same continuing source time, without repeating or skipping action.
- If the scene promises navigation through natural terrain, use native generated
  terrain and separated starts that require meaningful travel. A flat planted
  forest or two actors already facing each other does not demonstrate that task.
- Define the intended question and success condition before scouting takes.
  A selected successful take can illustrate a capability, but retain failed
  attempts and identify selection in the evidence. It does not estimate win rate.
  Do not quietly change models, equipment, terrain or controls to manufacture proof.
- Investigate apparent teleports, resets and discontinuities against source
  timestamps and traces. Re-record or replace broken footage instead of using
  a cut to imply continuous movement that did not occur. Stop before cleanup or
  reset commands become part of the demonstration.
- Clean drops and XP between matches. Inspect the arena for clutter before
  recording the next take.
- Capture a clean, overlay-free highlight while preparing the finale. It can
  provide a brief opening insert, while the later scene supplies context.
- Once the narrator's point and visual evidence are complete, cut dead waiting.
  A time-limit sequence need not run to its limit unless the elapsed wait is
  itself relevant evidence.

Offline rendering, simulation speed and motion smoothness are different issues.
A constant-FPS export does not prove evenly timed source motion. Use the existing
[replay timing guidance](PRODUCTION_LESSONS.md#smooth-offline-replay-footage)
before claiming smoothness. Deterministic tick-to-frame reconstruction remains
a development direction, not a capability proved by these edits.

## 4. Treat audio as continuous tracks, not attachments to picture cuts

The creator heard two overlapping narrators from the start, then noticed a music
discontinuity after a picture trim. These are whole-edit problems even if each
individual clip sounds correct.

- Assign speech ownership explicitly: embedded narration or a separate voice
  track, with deliberate mixing where needed. Do not play the old embedded voice
  alongside regenerated narration. Check the first seconds and every take join.
- Generate only changed speech sections in the established voice. Preserve
  complete takes at natural speed; fit picture duration to measured speech.
- Build music as a continuous bed across the edit, with intentional song
  transitions. A picture trim must not restart or splice the music arbitrarily.
  If duration changes, update song spans and ducking for the full revised edit.
- Ripple later events and narration together when inserting a slide. Keep the
  speech schedule non-overlapping and music present through inserted moments.
- Listen to the composed preview and final mix. ASR can check words; timestamps,
  sample counts and loudness checks can find technical failures. They do not
  establish that the delivery sounds natural or replace a listening review.

## 5. Give a call to action a viewer-facing reason

The original reused like/subscribe artwork was too small in a corner. The creator
wanted a centered, narrated moment, then rejected “Help this bot get better” as
self-interested. The later wording invited curiosity: “Could you beat its next
version?” and “See how it handles real players.”

For this style of video, put a short CTA at a natural middle break and another
after the closing point. Coordinate spoken words with a centered graphic or
dedicated slide; do not cover an important exchange or interrupt a sentence.
Connect subscribing to a specific next experiment the viewer might want to see.
Keep the like request brief. Do not imply that engagement directly trains the
bot. Reuse requested existing assets before creating unnecessary replacements.
Two placements and these exact phrases are project decisions, not a universal
formula or a measured engagement improvement.

## 6. Make revisions cheaper without creating a second current edit

| Stage | Earlier check or cheaper revision path |
| --- | --- |
| Start | Confirm repositories and branches, current timeline, voice/music choices, capture environment and upload access. Reuse shared pipeline UI code; keep job assets and scripts private. |
| Script | Maintain one current draft through the canonical timeline. Map each spoken claim to proof or an explanatory beat before producing every voice take. |
| Visual prototype | Review representative states and complete short motions before batch rendering. Check actual text bounds, sprite overlap, safe margins, connector endpoints and orientation. Geometry checks supplement comprehension review. |
| Capture | Probe one lit, unobstructed short take and its export. Save source timestamps and camera presets so replacing one angle does not require redoing the fight. |
| Edit | Use stable scene and take IDs, source hashes and dependency-aware caches. Replace the changed scene or voice, not every chapter. Avoid a new full-project bespoke script for each small correction where an existing operation fits. |
| Preview | Review the changed range with composed speech, music and graphics, including a little context on both sides. Source-only playback is a lower-fidelity view of the same timeline, not a second active cut. |
| Delivery | Reuse unchanged picture streams for audio-only changes when composition and timing allow it. Pre-size static art once instead of scaling a large PNG on every frame. Compose global overlays once; never bake and reapply them. |
| Verification | Use checks appropriate to the changed layer, then the required final delivery gates. Exact stream copy can use stream or pixel hashes; lossy composition needs a suitable decoded-image comparison. Do not demand byte identity after re-encoding. |
| Refresh | Bind the approved export to the exact timeline fingerprint. Normal timeline edits refresh through the shared workspace; a changed manifest binding or server code may require restarting only the owned preview server. Verify the actual player, not only a file on disk. |
| Upload | Verify the approved video and thumbnail before transfer, check channel identity, avoid duplicate uploads, save privately, and inspect saved metadata, thumbnail, processing and initial platform checks. Use the signed-in Studio workflow if saved API authorization is unavailable. |

The upload's description and chapter names are part of the edit's communication:
they must make sense before watching. Review title/thumbnail together at phone
size. Use a clear visual promise and readable minimal text, without claiming
unproved human superiority. Initial platform checks are not a guarantee against
later claims or restrictions. Public publication is a separate visibility action.
For replay geometry, seamless Shorts and content-specific AI-disclosure decisions,
see the [Minecraft Shorts review](MINECRAFT_SHORTS_PRODUCTION_REVIEW.md).

## 7. Improvements still to implement or validate

The following are follow-up design directions, not features added by this document:

- Dependency-aware affected-range delivery and QA, so a heading or one spoken
  CTA does not repeatedly trigger expensive whole-master comparisons of unchanged
  chapters. Keep final correctness gates and never promote a stale render.
- Reusable narration replacement with explicit speech ownership, complete-take
  fitting, overlap checks and music-duration/ducking updates.
- Reusable centered CTA inserts with editable copy, artwork and narration,
  rather than relying on this job's private scripts.
- Semantic review prompts for graphics: measured quantity, units, comparison,
  action, direction, timeline and selection state. Collision checks alone cannot
  detect an explanation that makes no sense.
- Deterministic tick-to-frame replay timing with validated interpolation and
  synchronized alternate cameras; measure action smoothness separately from FPS.

## Before the next master

1. Does the opening give a new viewer a reason to care and flow into the story?
2. Do the actual recorded words match the one current timeline?
3. Does each graphic explain its spoken claim without an unexplained symbol?
4. Are quantities labeled, comparisons fair, and selected examples distinguished
   from overall evidence?
5. Does capture show the promised task, with readable light and useful POV cuts?
6. Are the full speech mix and music continuous through every revised boundary?
7. Are CTAs brief, placed deliberately and tied to viewer curiosity?
8. Do thumbnail, title, description and chapters work without knowing model names?
9. Is the preview bound to the current approved edit, with pending work explicit?
10. Can this revision reuse verified sources instead of rebuilding unrelated work?
