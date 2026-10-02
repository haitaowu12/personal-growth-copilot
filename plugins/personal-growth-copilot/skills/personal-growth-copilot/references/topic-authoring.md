# Author and review a topic

Use the existing topic schema. Start with one task a learner should perform
independently, the intended audience and necessary prior knowledge. Avoid expanding
the topic catalog until the first journey can be reviewed and distributed reliably.

## Source to teaching decision

For each concept, record the inspected source section, the claim it supports, why
that evidence supports the claim, and its conditions or exceptions. Distinguish the
source's conclusion from your own explanation or example. Preserve edition,
coverage and uncertainty. Put source metadata in the pack's source records, and
map concepts through `source_ids`. Keep detailed review reasoning in the worksheet.
These are authored claims pending review, not proof the source was checked.

Work backwards from the objective: write an observable application and rubric,
then a diagnostic, explanation, misconception, worked example and practice. Make
the four question stages genuinely different tasks. Changing nouns alone may test
recognition of the same answer. Check a changed decisive assumption, missing input,
or applicability limit when relevant; do not force all three into every lesson.
Keep useful partial or conditional answers possible.

For practical work, ask the learner to expose the assumption, decision rationale
and verification check. A polished artifact or self-rating does not establish
independent capability. Offer help incrementally, respecting a request for a direct
explanation. Record help in any outcome study; an assisted answer is not unassisted
performance.

## Worked intake: requirements writing

This example uses the shipped pack's declarations, not a new inspection of NASA's
pages. The pack records selected-section access on 2026-09-07. Review the actual
passages before accepting the worksheet. All numerical scenarios are invented.

| Concept | Evidence and scope to inspect | Teaching decision and boundary to challenge |
|---|---|---|
| `obligation` | `nasa-c`: Appendix C, C.1/C.2/C.4; selected guidance | Separate independently testable obligations. The simple receipt example still lacks agreed content and timing; do not call it a finished baseline. |
| `measure` | `nasa-c` and `nasa-v`: clarity/testability and Product Verification 5.3 | Link a criterion to observable evidence. If an assumed time limit is withdrawn, retain the measurement method but stop claiming that limit is authorized. |
| `purpose` | `nasa-v` and `nasa-validation`: sections 5.3 and 5.4 | Distinguish compliance from intended use. A timing pass alone cannot establish that visitors complete the workflow. |

The examples above are visible teaching/development material. They cannot later
be called unseen transfer tests. The pack's delayed review questions are also
inspectable in the offline HTML. Reserve separate outcome tasks outside the lesson,
repository, package and ordinary retrieval; disclose who authored or saw them.

## Prepare the review

From the installed skill folder, with its declared Python dependencies:

```bash
python3 scripts/review_learning.py prepare --pack assets/learning/requirements-writing.json --out /chosen/review.json
python3 scripts/review_learning.py render --pack assets/learning/requirements-writing.json --review /chosen/review.json --out /chosen/review.md
```

The JSON worksheet and readable Markdown enumerate every source, concept, question
with all answer choices/feedback, and writing rubric. Nothing starts approved. The
exact topic byte hash, item contents and checklist are fixed. The reviewer edits
only `reviewer` and each item's `decision` (`pending`, `accept`, `revise`) and `notes`
in the JSON. Include evidence locators and reasoning, alternative valid answers,
and remaining issues in notes. Supply name, relationship to author and an RFC 3339
`reviewed_at` date-time when recording judgments. This is attribution, not verified
identity or independence. Use a new filename to render a changed worksheet.

```bash
python3 scripts/review_learning.py check --pack assets/learning/requirements-writing.json --review /chosen/review.json
python3 scripts/review_learning.py check --pack assets/learning/requirements-writing.json --review /chosen/review.json --require-accepted
```

Ordinary `check` verifies structure and reports pending/revise/accept counts.
`--require-accepted` returns exit 2 for pending items or requested changes; invalid
records return exit 1. All-accepted means judgments were recorded, not that their
truth, reviewer independence, learning benefit or release readiness was verified.
Existing different output files are never overwritten. Scripts do not browse,
fetch sources, send review material, or change the topic.

When topic bytes change, increment the topic version for teaching changes and
prepare a new worksheet. Preserve the old review; use its findings as leads but
do not carry acceptance automatically. Resolve requested changes with the reviewer.
Keep completed worksheets and reviewer details outside the learner distribution.

## Decide what improved

Check integrity, source fidelity, task performance and human usability separately.
Use the same source and matched tasks when comparing a teaching change. Preserve
ties, losses, missing follow-up and unnecessary abstention. Do not retune on reserved
outcomes and reuse them as a fresh holdout. A null result may justify keeping the
simpler method. Passing code checks only establishes the tool's tested behavior.

Distribute only the reviewed/versioned topic, player, skill and checksums through
the existing allowlisted packaging workflow. Browser acceptance, independent
content review, clean-host recovery and the consented learner pilot remain separate
gates. The worksheet does not satisfy or replace the release qualification record.
