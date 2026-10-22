# GTNH Shorts: process, evidence and efficient revisions

Reviewed 2026-10-22 after the Forge Hammer and Macerator episodes. These are
observed production lessons and creator preferences, not audience-performance
findings or a claim that the shared pipeline automates the checks below. Keep
recordings, source audits, render receipts and upload credentials in the private
workspace. Read with the [editorial guide](EDITORIAL_GUIDE.md),
[Minecraft Shorts review](MINECRAFT_SHORTS_PRODUCTION_REVIEW.md) and
[persistent footage index](FOOTAGE_INDEXING.md).

## Tell the process, not just the machine

Repeated beauty shots around the finished machine made the first assembly feel
boring. Build the story around a dependency chain: need -> materials -> obstacle
-> preparation -> construction -> working result. Short cuts should add steps
or useful perspectives, rather than orbiting the same finished object.

For these episodes, cheaper plates justified making the forge hammer before the
macerator. Red-alloy preparation needed room because obtaining and processing
redstone, washing dust, smelting alloy and making piston components were part
of the achievement. The macerator story included the bronze pickaxe's mining
limit, training the tool, harvesting diamonds and adding a second boiler when
the workshop outgrew its steam supply. These are case-specific dependencies;
verify the next pack/version and recorded save rather than copying this order.

For this GTNH series, use shader AgenticReplay footage for actions and cinematic
views, and original first-person footage when explicit UI evidence is needed.
Capture gathering, mining, processing, crafting, infrastructure changes and
operation. Preserve acquisition provenance: an edited progression montage,
especially one containing supplied items, does not establish an uninterrupted
survival acquisition chain.

## Bind each claim to the right evidence

| Correction from these edits | Reusable decision |
| --- | --- |
| Redstone was called iron. | Identify the actual item/block from the recording and relevant UI; check mechanics against the exact pack's source or recipe overrides. Historical narration and visual resemblance are insufficient. |
| Alloy-smelter UI appeared while the voice listed macerator ingredients. | Inspect the entire selected source interval, including menu changes. Keep the correct recipe visible through every ingredient in the sentence, not just its opening words. |
| Tool leveling initially used a still image. | When the claim is about an action or state change, show moving evidence of that action and notification. A zoom/pan can guide attention to UI text without replacing the event. |
| Red alloy was treated as a trivial prerequisite. | Allocate screen time to nontrivial preparation and show its intermediate steps. Compress repetition, not the causal explanation. |
| Narration described an editing operation: the cycle was skipped. | Describe the mechanic naturally: "This ore takes forty seconds to crush." Keep the recipe-specific duration accurate and retain the source timing/condensation in private edit provenance. |
| The macerator explanation focused only on ore. | Add a few useful non-ore examples after verifying that this machine tier can actually execute them. Do not inherit bonus outputs or recipe access from later tiers. |

Use a declared actual-frame hold for a recipe, tooltip or input/output count
when readability needs it. Keep the source timestamp and crop. Such a hold can
prove a displayed state; it cannot substitute for filmed mining, leveling,
washing or a continuously running machine cycle. Do not imply real-time waiting
when a cycle has been condensed.

Keep technical item names only when they help the viewer. Generic "ore" was
enough here; a named-ore JEI detour distracted from the machine's purpose.
Scope yield comparisons to the demonstrated recipe, not every ore or final
smelting output. The observed hammer comparison was three ingots -> two plates
versus two -> one by hand: 25% less metal per plate, not a universal ore-doubling
claim.

## Make portrait UI readable without surrounding it with labels

Remove routine top headings that repeat the narration. Crop to the relevant
ingredient grid, counts or tooltip, retain useful context, and use a softly
blurred recorded background when a narrow UI panel cannot fill the portrait
frame. Review at phone size. A decorative background may loop; the foreground
action must not accidentally repeat.

Use compact captions close below the focused UI panel, with contrast and safe
placement checked per shot. Keep occasional callouts that add information:
ratios, a mining-level gain, cycle duration or non-ore examples. Remove redundant
topic labels. Any crop, zoom or pan must keep the claimed item/count visible
throughout its matching words.

For this series, preserve the older episode identity: authentic GTNH logo fades
in/out, Part number below it, opening narration beginning "In GTNH, ...", and a
brief spoken like/share/subscribe ending with fading graphics over moving
footage. Reuse approved logo/shape assets before generating new artwork. These
are series preferences, not mandatory branding for other projects.

## Qualify replay state before a batch

The disconnected pipes were a replay-state defect, not something to conceal
with camera framing. In this profile, asynchronous tile-description parsing
could apply an older state after newer replay events during fast seeks. The
owning code was fixed and replacement native takes checked against recorded
connection states. This is profile-specific evidence, not universal replay/mod
compatibility certification.

Before a large batch, test a short advancing take at the intended source time:
machine connections, orientation, operation, actor visibility and shader output.
Check representative seeks as well as linear playback. Fix runtime defects in
the owning code, record the built and installed revision, reject stale takes,
and retake only affected shots. If the selected AgenticReplay distribution
includes ReplayMod, remove the duplicate standalone jar from that filming
profile. Verify the actual package rather than assuming every version bundles it.

Check source ranges across adjacent clips. The opening accidentally replayed
the same mining action because two cuts used overlapping ranges of one short
take. Use a distinct establishing view, one continuous action selection and
unused detail frames. An intentional replay should have an editorial reason;
camera variety alone does not make duplicated action new footage.

## Keep revisions cheap and delivery traceable

Stay in the shared editor and short range previews while the edit changes.
After approval, derive a frozen delivery plan from the canonical timeline and
record its revision/hash. Export the approved edit, not an older file whose
name still says "master". Preserve frame-grid timing and scale graphic sizes
and positions together when changing resolution. A 1080p export containing
540p review assets does not recover native 1080p detail; retain native assets
where available and record mixed-resolution limitations honestly.

Reuse unaffected composed ranges only when picture, graphics and timing agree.
For picture-only changes, preserve the approved audio. For a sentence correction,
patch that sentence with matching voice, restrained delivery, pace and level;
listen in context and retain surrounding speech. A configured voice name alone
does not guarantee consistent delivery. Distinguish unchanged PCM samples or
encoded packets from approximate similarity after a lossy re-encode.

The music brief here is chill, dreamy and whimsical Steam Age, not intense
industrial action. Give each episode its own gentle theme: warm craftsmanship
for the hammer, curious clockwork discovery for the macerator. Keep music under
speech with ducking and fades. Avoid dramatic builds, harsh machinery and loud
percussion unless the creator asks. Review the mixed voice and music, not just
isolated stems.

Global PNG overlays can be expensive even when visible briefly: the current
renderer loops their inputs for the full program. Do not assume a tiny graphic
change makes a full export cheap. Profile before promising speed; use range
previews and safe reuse. Time-bounded overlay processing remains an optimization
opportunity, not a feature demonstrated by this production.

Before upload, run full decode, frame/rate/duration and audio checks, inspect
black gaps and sample composed frames around corrected claims. Check upload
access early. If OAuth expires, verify a successful callback and saved channel
identity; a browser click alone does not establish restored authorization.
Keep resumable upload URLs private, save the returned video ID immediately,
and inspect existing receipts before retrying. Verify requested visibility and
HD processing separately. API processing success does not establish that all
Studio copyright checks were inspected. Assess disclosure from actual media
and current platform guidance; generated music is a separate consideration
from gameplay, title assistance and generic narration.

## Retain enough to reuse the edit

Index once, then inspect shortlisted source ranges densely. Ten-second sampled
coverage is not continuous audiovisual review or a full transcript. Correct the
stored context when a source item or action was misidentified.

Delete raw recordings only within the user's authorized scope and after the
required delivery verification. Retain selected shot assets, canonical timelines,
captions, narration/music, final exports, source fingerprints and replay files
unless their removal is also requested. Record exact files and recovered bytes,
and mark deleted sources unavailable in the manifest and context index. An index
preserves descriptions and timecodes, not the deleted footage itself.

Useful future automation: claim-to-shot anchors that survive timing edits;
warnings for overlapping action ranges or a recipe menu changing mid-line;
and source-availability checks before cleanup. These remain proposed checks,
not existing CLI guarantees.
