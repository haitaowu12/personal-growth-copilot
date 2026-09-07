# Source-grounded learning release

## Scope and acceptance

Deliver one complete, offline learning journey for writing verifiable requirements,
plus a reusable topic-pack format and explicit conversational learning lane. The
learner diagnoses a defect, receives targeted feedback, studies a worked example
when needed, solves a different scenario, writes a requirement, checks a rubric,
and returns for delayed retrieval. This is educational practice, not engineering
approval, certification, or demonstrated product efficacy.

The browser player is the supported reference host for this learning lane. It has
no model, server, account, telemetry, network requests, or automatic persistence.
Coaching safety and sensitive growth-record persistence retain their existing gates.

Acceptance at the public seams:

1. Topic validation rejects missing evidence, unsafe URLs, duplicate IDs,
   unresolved prerequisites, cycles, malformed questions, and unsupported versions.
2. Deterministic build produces one portable HTML file from the complete installed
   skill folder. No source file outside that folder is required.
3. The reducer selects remediation after a wrong diagnostic and a new application
   after a correct one; hints and repeated attempts remain visible.
4. First attempts remain immutable. Feedback uses authored rationales. Free text
   receives an explicit self-review rubric, never fabricated automated grading.
5. Delayed review cannot complete before its due time. Progress binds exact topic
   bytes; imports validate and replay events, never trust derived scores.
6. Users can resume, export, import, and clear progress. Device storage is opt-in;
   import does not enable it. Malformed files leave the current session intact.
7. Desktop, narrow-screen, keyboard, error, storage-denial, offline, and full journey
   behavior receive browser evidence. Exports are user-controlled practice records.
8. Problem reports remain local, content-free candidates for author review. They
   never alter published content or silently supply learner work to an agent.

## Design

- Surface: focused practice workspace for adults, on desktop and phone. One current
  task, concept navigation rail, and optional source/explanation panel.
- Authority: no existing visual system. Warm neutral canvas, dark ink, teal accent,
  system sans text, restrained serif headings. No remote fonts or imagery.
- Visual thesis: a quiet annotated workbook with a clear next action.
- Information: overview, three concepts, progress/review, and source notes.
- Interaction: short feedback reveal, visible progress, strong keyboard focus;
  reduced-motion support. Content is plain text rendered with DOM APIs.

## Architecture

`topic JSON -> Python schema/semantic validator -> deterministic HTML builder`

`learner action -> JavaScript reducer -> replayable progress -> browser UI`

One reducer owns transitions in browser and Node tests. Python owns topic validation
and distribution. Explicit prerequisite edges replace arbitrary graph-depth labels.
No duplicate curriculum or second coaching record store is introduced.

## Evidence boundaries

Selection accuracy, help use, and attempt history describe observed practice.
Writing checks are self-reported. Review intervals (7 days, then 21 days) are a
configurable product policy, not an empirically optimized personal schedule.
The browser clock and imported files are user controlled. No certificates,
anti-cheating claims, independent mastery claims, or efficacy promotion are made.

See `LEARNING_PILOT.md` for prospective evaluation. Existing release qualification
remains blocked until its independent gates pass.
