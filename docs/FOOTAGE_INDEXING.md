# Persistent raw-footage context index

Creator preference recorded 2026-10-22: index the whole raw video once, save the
context of each small part with source time ranges, and reuse that record to
choose clips later without repeating the full analysis.

This is the preferred workflow for raw footage intended for reuse. The existing
CLI provides source-bound shot, sample and transcript evidence; the richer
semantic context record described below is an editorial requirement, not a
claim that the CLI already generates or searches those descriptions.

## Index once, select clips many times

1. Identify the original source with its full SHA-256, asset ID, duration,
   selected video/audio streams and timing metadata. Keep the original intact.
2. Work through the entire source chronologically. Divide it into small,
   meaningful action, topic or scene segments; subdivide long continuous takes
   even when no visual cut occurs. Use finer coverage around fast events and
   reactions. Do not restrict the index to moments selected for the current edit.
3. Save factual context and timestamped dialogue separately from editorial
   judgments. Retain quiet, repetitive and apparently uninteresting sections;
   another edit may need them. Record unavailable speech or unclear visuals
   explicitly rather than inventing context.
4. Maintain a readable chronological index and a structured companion with the
   same stable segment IDs and revision. Store both, transcripts and supporting
   evidence in the private job/project workspace, outside public Git content.
5. Search the saved context, dialogue and tags for subsequent requests. Return
   source IDs and candidate in/out ranges; inspect shortlisted boundaries for
   complete sentences, reaction tails and clean transitions before cutting.
   Record corrections or added detail in the index for future reuse.

Full-duration coverage means every interval is accounted for, including explicit
unreviewed or uncertain ranges. It does not mean every frame has been inspected.
Sparse contact sheets or detected shot boundaries alone do not establish that
the whole video has been semantically reviewed. Record the actual sampling and
audio-review coverage; leave the index partial until gaps are resolved.

## Segment record

| Field | Required meaning |
| --- | --- |
| Identity | Stable segment ID and the exact source asset ID/hash. |
| Source range | Numeric start/end in source-media seconds, with readable timecodes. Define ranges as start-inclusive/end-exclusive. State the time origin and mapping to decoded stream timestamps; retain rational frame rate/time base and stream offsets. For variable-rate footage, use observed presentation timestamps rather than assuming constant frames per second. |
| Context | What happens, the subject/topic and why the action matters; concrete enough to select the segment without rereading the footage. |
| Dialogue | Timestamped transcript references, speakers when established, and relevant quotes; mark missing or uncertain transcription. |
| Visuals and sound | Visible actions, on-screen text, reactions, camera changes, important sounds and relevant quality problems. Distinguish visual inspection, audio review and transcript-only evidence. |
| Dependencies | Related segment IDs and any setup/payoff needed to understand the moment, including context outside the suggested cut. |
| Search tags | Subjects, events, people when established and other useful literal search terms. |
| Editorial notes | Optional hook, reveal, explanation, funny moment or other clip potential; keep subjective judgments separate from observed facts. |
| Clip handles | Optional suggested cut range and available lead-in/tail; do not replace the factual segment range with a single edit choice. |
| Evidence and coverage | Inspected frame timestamps/references, audio/transcript coverage, review method, uncertainty and any unreviewed subranges. |

The index header should include its schema/analysis version, revision, creation
and update times, analysis settings and source provenance. Semantic records can
live in a versioned JSON sidecar paired with a readable Markdown table; these are
proposed editorial artifacts, not additions to the current CLI schema. Link to
existing evidence by asset ID and source range rather than editing SQLite rows
or adding unsupported fields to timeline JSON.

## Reuse and invalidation

Reuse completed records when the source identity, timing and relevant analysis
inputs still match. A new clip request, new editorial angle or timeline reorder
does not require full reindexing. Preserve factual records when only editorial
notes change. Repair a missing description or uncertain moment locally, retaining
completed work and updating its review coverage.

Changed source bytes, a changed time mapping or incompatible analysis settings
require explicit revalidation of affected records. Never silently apply old
timestamps to a trimmed, transcoded or replaced file. Keep original source ranges
separate from edited-timeline positions. Missing evidence should be flagged and
restored where needed, not treated as reviewed content.

This trades a larger first-pass effort and storage cost for cheaper repeated
selection. No measured speedup is claimed. Final clip-boundary checks remain
useful; full reindexing should be reserved for invalidated or insufficient
coverage.

## Current implementation boundary

See [the footage evidence API](API.md#footage-evidence). The current SQLite index
stores FFmpeg scene-score boundaries, observed samples and supplied transcript
segments/words, keys reuse by source/settings, and rejects stale sources during
queries. Without supplied samples it currently prepares eight sample frames;
that is an overview, not comprehensive semantic coverage. Text queries search
literal transcript text only.

Whole-video semantic segmentation, context/tag search, a paired readable and
structured context export, and segment-level semantic resume remain future
implementation work. Until implemented, maintain the context artifacts as part
of editorial review and disclose actual coverage. Existing local-only/provider
authorization rules still apply; this workflow does not introduce automatic
uploads, model downloads or paid analysis calls.
