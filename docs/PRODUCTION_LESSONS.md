# Production lessons and a faster workflow

Reviewed 2026-10-07 after the Endless showcase; replay motion guidance added
2026-10-18; Minecraft AI editorial and efficiency retrospective added 2026-10-19.
Minecraft Shorts capture, revision, loop and upload lessons added 2026-10-21.
These are reusable production
rules, not a claim that the pipeline already automates every check below.
Project footage, prompts, scripts, credentials, world data and QA receipts stay
in private job workspaces.

See the [Minecraft Shorts review](MINECRAFT_SHORTS_PRODUCTION_REVIEW.md) for
recorded-scene camera/actor checks, DH coverage, selective retakes, looping edits
and the creator's AI-disclosure preference.

## What the production demonstrated

- Short, independently replaceable shots made late revisions practical. The
  final edit kept 29 cuts rather than depending on one long recording.
- Complete narration needed room: repairing the nine-take voice edit extended
  the runtime from 84.5 to 98.55 seconds. Existing footage handles covered the
  extension; recording more scenes was unnecessary for that repair. Verification
  confirmed native speed, preserved source sample counts, no voice in the gaps,
  and a minimum gap of 0.74 seconds. That gap is a case result, not a universal
  pacing rule.
- A later removal of two voice sections retained seven complete takes and the
  same picture. Copying the encoded video stream and remixing audio preserved
  its verified stream hash, avoiding another picture encode.
- Successful capture metadata did not guarantee a usable image: some captures
  were black or obstructed. Actual image inspection caught those failures.
- A working mechanism did not guarantee a convincing shot. A visually detached
  elevator rope needed a source fix, runtime verification and replacement footage.

The production receipts support those results. They do not measure total hours
lost, thumbnail CTR improvement or a general cause for the black captures.
Do not invent those conclusions from revision counts or export success.

## Where time was wasted, and how to prevent it

| Rework | Cause or observation | Earlier check / cheaper recovery |
| --- | --- | --- |
| Rewriting narration after filming and repeated voice generation | Technical detail, commercial phrasing and references to a workshop did not match the audience or the visible platforms. | Approve the main claim and plain-language script against a shot map. Describe only what the viewer can see; omit filler and unnecessary caveats. |
| Speech sounded clipped and rushed | Estimated word timestamps drove internal cuts; some takes were accelerated to fit fixed windows. | Generate short sections, keep complete takes at native speed, and fit the picture to measured speech. Use word timestamps for alignment, not automatic cut boundaries. |
| Replacing music and transition effects | The supplied music and preference for clean cuts were settled late; available SFX tooling had become an editorial default. | Confirm the music and audio style early. Clean cuts and natural audio are the default; synthetic whooshes/risers require an explicit request. Update guidance when a preference changes. |
| Rebuilding the hero structure | A distant view hid the missing ground connection. | Survey terrain, foundations and access before detailed construction. Review ground-level, side, roof and wide views before committing to final filming. |
| Re-recording static or short-distance hero views | Camera motion and distant terrain were evaluated too late. | Preview moving orbits/ascent and the intended render distance before a recording batch. Warm and verify terrain/LOD data for the same world. |
| Re-recording mechanical proof | Functional checks missed a visible rope defect. | Test mechanics and final rendered appearance, including passengers and representative heights, before recording polished takes. Fix source defects and verify the installed artifact before retakes. |
| Reworking proof overlays | Coordinates appeared too briefly, and the vanilla limit needed a clearer visual reference. | Keep proof visible for the entire relevant line. Align a label/arrow to the actual target and review tracking throughout the shot. Keep distinct locations and heights unambiguous. |
| Reopening the filming environment for documentation art | Ground-up and other publication views were requested after the main filming batch. | Capture a reusable thumbnail/banner/demo set while the world and camera are ready, including clean title-space and ground-up views. |
| Repeated unusable captures | Guessed eye height, vegetation occlusion and recurring black captures. | Probe ground and camera clearance, inspect a cheap preview, then export. If black captures recur within a session, reopen it and verify the first capture; treat that as a workaround, not a proven root cause. |
| Infrastructure diagnosis and migration | High host CPU steal complicated recording. | Separate guest CPU work from host scheduling contention before tuning game code. Check host health early; preserve world backups and move only owned services if needed. |
| Long exports for small revisions | Changes to speech or music unnecessarily risk a full picture render. | Preview changed ranges first. Reuse verified cuts; for unchanged picture, use an explicit audio-remix/stream-copy workflow and verify stream identity. |
| Late upload authentication work | Expired authorization or insufficient scopes surfaced near delivery. | Verify the target channel and upload permissions early. Prepare metadata and thumbnail before transfer; retain private resumable-upload state to recover without duplicate uploads. |
| Failed preparation followed by launch attempts | Fragile nested command quoting and dependent steps without a failure gate. | Use structured arguments or saved scripts. Stop dependent stages on failure; launch only after preparation succeeds. |

## Workflow for the next video

For the creator's detailed corrections during the Minecraft AI video, read
[the 2026-10-19 production review](MINECRAFT_AI_PRODUCTION_REVIEW.md).
Its key additions are viewer-first hooks and packaging, concrete rather than
decorative graphics, continuous audio through picture revisions, meaningful
gameplay demonstrations, and centered spoken CTAs with a reason to return.
The review also separates working practices from pipeline improvements still
to implement; it makes no measured engagement or time-saved claims.

Maintain one canonical timeline per workspace, including draft scenes and their
narration. Revise that edit as work progresses; do not keep an older assembled cut
and a separate current storyboard as parallel active versions. Full-script views
and previews must use that timeline. Keep earlier exports only as history, mark
missing narration/visuals explicitly, and invalidate exports when the edit changes.
See [the workspace contract](WORKSPACE.md).

1. **Lock the promise and creative direction.** Write one clear viewer-facing
   claim, an opening hook, proof and a short call to action. Confirm music, voice,
   logo and transition style. Use the speaker's chosen pronouns consistently.
   Keep the script direct; technical details belong only where they help explain
   the visible result.
2. **Check the environment before expensive work.** Verify source/build versions,
   server health, backup/recovery, native capture, encoder availability, disk
   space and upload authorization. Run a small capture and encode probe. On a
   shared machine, establish isolated/background capture before launch, honor
   desktop-control restrictions, and limit CPU/memory use.
3. **Approve the subject in multiple views.** Confirm foundations and camera
   access, inspect the final game framebuffer, and demonstrate the advertised
   mechanics. Do this before detailed hero filming. Server state alone cannot
   prove how the viewer will see the result.
4. **Create a shot-to-line map.** For each stable shot ID, record the claim it
   supports, required on-screen evidence, source handles, camera preset and
   replacement options. Match a system explanation to that system's footage;
   save hero architecture for the hook and payoff when appropriate. Coordinate
   proof must stay visible throughout its associated speech.
5. **Record short takes with handles.** Capture several usable angles and motion
   options, with extra time at both ends for pacing changes. Save native camera
   presets and source provenance. In the same batch, capture wide, ground-up,
   crown and lighting variants for thumbnails and documentation. Inspect every
   exported image/clip for black frames, occlusion and framing.
   For replay footage, also pass the motion checks below before a recording or
   export batch; a successful encode does not establish smooth movement.
6. **Generate narration in short sections.** Keep a consistent voice and settings,
   review each section for pronunciation and tone, and regenerate only failed
   sections. Measure actual durations before final timing. Preserve complete
   speech and natural pauses; leave an audible breath between takes. Extend
   suitable picture handles or add useful footage when necessary, then ripple
   later voices, titles, arrows and music together.
7. **Review a cheap draft before the master.** Preview changed ranges with the
   final audio mix and overlays, then review the whole draft for narrative flow.
   Listen for clipped words, competing voices and music masking speech. Check
   the proof and CTA against the actual picture. Lock these decisions before
   the expensive final encode.
8. **Export only the changed work.** Use source-bound caches and verify handle
   bounds. Choose an encoder/quality/size tradeoff after a short probe, not during
   a long export. For an audio-only edit, copy picture only when picture timing,
   overlays and content are unchanged; verify the resulting video stream hash.
   Keep the previous approved master until the replacement passes QA.
9. **Verify delivery, then package and upload.** Fully decode the final MP4 and
   check duration, frames, audio streams and player-compatible output settings.
   Listen to the finished mixed audio; ASR and sample checks supplement listening
   and cannot prove natural delivery. Build the editable package after approval,
   using portable asset references, complete voice takes and verified hashes.
   Upload privately first and check processing, thumbnail, metadata and platform
   restrictions before changing visibility. Processing success is not copyright
   clearance or public publication.
10. **Close the job cleanly.** Preserve receipts and the approved revision locally,
    restore only settings changed by the job, and close only owned processes.
    Record reusable findings separately from private project data.

## Review animated layouts before delivery

A successful encode does not establish a readable explanation. Inspect every
distinct graphic state at full output size, including the frames immediately
before and after state changes. Sample moving elements at their travel limits.
Review actual composed chapter frames as well as source drawings.

Give character art, labels, values and diagrams separate space. Connectors should
have clear endpoints and avoid crossing text or character art; remove a connector
when grouping or one highlighted readout communicates the relationship more
clearly. Check small repeated panels separately: shrinking the container without
shrinking and spacing both characters can make them overlap.

Where the renderer exposes geometry, check actual font bounds, sprite bounds,
connector paths and safe-frame margins throughout the rendered animation. These
checks supplement visual review; they do not establish narrative clarity or
replace inspecting the finished picture in the viewer.

## Smooth offline replay footage

Offline rendering should make output timing independent of rendering speed.
A slow machine may take longer to export each frame; that alone should not
cause pauses in the finished video. A replay normally reconstructs recorded
client-visible updates, rather than rerunning the original AI and server
simulation. Evenly spaced output frames can therefore reproduce uneven source
updates. A constant frame rate in FFprobe is not proof of smooth action.

For future gameplay videos:

1. **Define the simulation clock before recording.** Record an authoritative
   tick index and its relationship to replay timestamps. For a normal Minecraft
   simulation at 20 ticks per second, tick `n` belongs at `n * 50 ms` relative
   to the simulation start. Preserve deliberately different tick rates and
   intentional pauses as explicit choices. Manually stepping a simulation and
   sleeping between requests does not guarantee evenly timed recorded updates.
2. **Preserve enough timing information to reconstruct motion.** If input or
   recording runs behind, use the authoritative tick mapping to place updates
   on the intended timeline. Preserve packet/event order and align sound,
   effects, markers and camera paths to the same clock. Simply speeding up an
   entire clip does not remove irregular gaps between updates. If an existing
   recording lacks a reliable mapping, establish one or make a new recording
   before claiming its timing has been corrected.
3. **Verify interpolation, then choose output fps.** Confirm that the replay
   advances fractional ticks and interpolates entity movement and camera motion
   correctly. Check abrupt movement updates and camera keyframe boundaries.
   Use 60 fps as the target for smooth gameplay footage unless the delivery
   calls for another rate. Raising fps alone, duplicating frames or applying
   optical flow does not establish correct simulation timing.
4. **Review a short moving sample before the batch.** Include a camera pan,
   lateral character movement and a combat impact. Inspect normal playback and
   consecutive frames for unintended holds, jumps, uneven cadence and audio
   drift; account separately for intentional pauses and end-frame holds. Verify
   both the exported file and browser playback. Separate source motion problems
   from player decoding problems rather than assuming either is the cause.
5. **Keep evidence and preserve previous footage.** Retain the clock mapping,
   export settings and sample review result in the private job. Only regenerate
   the remaining shots after the sample passes, and keep previous approved
   exports until replacements pass review.

This is production guidance and deferred implementation work, not a claim that
the pipeline currently retimes replay packets or automatically validates motion
cadence. Full decode, black-frame checks and correct frame counts remain useful,
but do not replace reviewing motion.

### Rerecording a stalled observer replay

A recorder that assigns timestamps on the client main thread can turn a client
stall into a long hold followed by many movement updates at once. Warm the
arena and shaders before movement, reduce the recording viewport and view
distance, and let the observer acknowledge work between simulation steps.
Offline export can still use full resolution and the intended shader settings.
Check the new packet cadence and compare every native tick with the original
run before replacing footage. Exclude a deliberate stationary tail from missing
movement checks, but retain checks for internal gaps and bursts. Preserve the
old take and review the exported route through obstacles, not just the outcome.
These checks may be implemented by a private capture adapter; they are not a
general built-in pipeline motion validator.

### Keep music continuous through picture trims

Removing a quiet gameplay interval should not remove the same samples from a
precomposed music bed. That produces an audible jump even when speech and
picture remain aligned. Keep song phase independent of picture cuts, rebuild
from uninterrupted source spans for the current duration, and crossfade changes
between songs. Duck against the current narration placements rather than an old
speech bed whose timings preceded the trim. Keep speech complete and check the
new full mix after delivery.

For the Minecraft production, the repaired music uses the three supplied songs
with 2.5-second equal-power transitions. A source-sample comparison across the
previous picture trim verifies that the first song remains uninterrupted; a
full-length silence scan and final-mix decode/loudness checks cover delivery.
This is a private production recipe, not a general automatic music-editing
feature in the pipeline UI.

## Improvements to implement next

These are proposed development priorities, not existing CLI options:

| Priority | Pipeline improvement | Completion evidence |
| --- | --- | --- |
| 1 | Narration scheduling that defaults to complete native-speed takes, checks overlap and reports insufficient visual handles before export. | A synthetic long-voice fixture extends suitable visuals or fails clearly, without dropping samples or silently accelerating speech. |
| 1 | An audio-only delivery path that preserves picture and runs final-mix QA. | Encoded picture stream identity, successful full decode and the expected changed audio are verified. |
| 2 | Shot context/evidence anchors and a ripple preview for voice, overlays and music. | Extending a line keeps its proof visible and updates later anchors consistently. |
| 2 | A capture adapter with cheap previews, black-frame detection and bounded recovery. | Bad captures cannot become approved assets solely because the capture request succeeded; retries remain limited to owned sessions. |
| 2 | Replay timing provenance and a short motion review before batch export. | A deliberately uneven source-update fixture is distinguished from valid constant-fps output; a verified tick mapping preserves event order and audio alignment, and a moving 60 fps sample passes review before a full batch. |
| 2 | Upload preflight and durable resumable transfer recovery in an optional publishing adapter. | Expired/wrong-channel authorization is detected before transfer; interruption resumes the same upload without duplicate publication. |
| 3 | A local stage record for creative approval, recording, narration, draft, master QA and delivery. | Invalidated approvals are visible after edits, and unchanged artifacts are reused by verified identity. |

Use the [editorial guide](EDITORIAL_GUIDE.md),
[setup and rendering instructions](../README.md),
[timeline validation and preflight](TIMELINE.md), and
[operations/recovery](OPERATIONS.md) alongside these production checks.
Add regression coverage when the proposals become implementation changes; this
document does not establish new schema fields or automated approval gates.

## Packaging and image lessons

Ground thumbnail concepts in actual footage and the video's story. A stylized
generated illustration can communicate a truthful learning or transformation
idea, but must not pretend to be a proof screenshot or imply an unshown victory.
Keep one legible subject and a clear visual promise, without assigning a height
or capability to a scene that does not demonstrate it. Generated banner art can
stylize a reference; demonstration images should accurately show the captured result. Review logo
spelling, transparency and readability at the intended display size.

Capture reusable art early, but package only the approved versions. For public
documentation, check asset links and rendered sizes, remove obsolete references,
and verify remote assets match the intended files. Keep runtime icons separate
from promotional banner replacement. Thumbnail ideas are hypotheses until real
audience results support them; local visual approval is not evidence of higher
CTR.
