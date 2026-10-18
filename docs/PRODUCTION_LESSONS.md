# Production lessons and a faster workflow

Reviewed 2026-10-07 after the Endless showcase. These are reusable production
rules, not a claim that the pipeline already automates every check below.
Project footage, prompts, scripts, credentials, world data and QA receipts stay
in private job workspaces.

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

## Improvements to implement next

These are proposed development priorities, not existing CLI options:

| Priority | Pipeline improvement | Completion evidence |
| --- | --- | --- |
| 1 | Narration scheduling that defaults to complete native-speed takes, checks overlap and reports insufficient visual handles before export. | A synthetic long-voice fixture extends suitable visuals or fails clearly, without dropping samples or silently accelerating speech. |
| 1 | An audio-only delivery path that preserves picture and runs final-mix QA. | Encoded picture stream identity, successful full decode and the expected changed audio are verified. |
| 2 | Shot context/evidence anchors and a ripple preview for voice, overlays and music. | Extending a line keeps its proof visible and updates later anchors consistently. |
| 2 | A capture adapter with cheap previews, black-frame detection and bounded recovery. | Bad captures cannot become approved assets solely because the capture request succeeded; retries remain limited to owned sessions. |
| 2 | Upload preflight and durable resumable transfer recovery in an optional publishing adapter. | Expired/wrong-channel authorization is detected before transfer; interruption resumes the same upload without duplicate publication. |
| 3 | A local stage record for creative approval, recording, narration, draft, master QA and delivery. | Invalidated approvals are visible after edits, and unchanged artifacts are reused by verified identity. |

Use the [editorial guide](EDITORIAL_GUIDE.md) and the
[setup and rendering instructions](../README.md) alongside these production
checks. Add regression coverage when the proposals become implementation changes;
this document does not establish new schema fields or automated approval gates.

## Packaging and image lessons

Use actual footage as the foundation for thumbnails. Keep one legible subject
and a clear visual promise, without assigning a height or capability to a scene
that does not demonstrate it. Generated banner art can stylize a reference;
demonstration images should accurately show the captured result. Review logo
spelling, transparency and readability at the intended display size.

Capture reusable art early, but package only the approved versions. For public
documentation, check asset links and rendered sizes, remove obsolete references,
and verify remote assets match the intended files. Keep runtime icons separate
from promotional banner replacement. Thumbnail ideas are hypotheses until real
audience results support them; local visual approval is not evidence of higher
CTR.
