# Topic packs and distribution

The first pack is `requirements-writing` version `1.0.2`, in the installed skill's
`assets/learning/` folder. It is an original educational synthesis with anchored
NASA guidance. Numbers and project facts in exercises are invented assumptions.

A pack contains title, audience, duration estimate, review intervals, source records,
and concepts. Each concept supplies an explicit prerequisite list, source IDs,
objective, explanation, misconception, worked example, four distinct questions,
and a written application with self-review criteria. Plain text only; no HTML,
executable instructions, imported scripts, or network fetches from pack content.

The compiler enforces the adjacent JSON Schema and checks IDs, reference closure,
prerequisite cycles, answer-key membership, safe HTTPS source links, distinct question
prompts, and increasing review intervals. It orders concepts by prerequisites once.
Human source review is still needed: valid JSON is not proof of true claims or a
correct answer key.

## Author/update workflow

Use the portable [authoring recipe and worked intake](../plugins/personal-growth-copilot/skills/personal-growth-copilot/references/topic-authoring.md).
`scripts/review_learning.py` inside the skill prepares an exact-topic review
worksheet and a readable dossier covering every source, concept, answer key and
writing rubric. Its checker detects stale or incomplete records; it cannot verify
human independence or the truth of recorded judgments. Worksheet schema 1.1 also
displays headline claims, estimated duration and review intervals. Regenerate older
worksheets with the current tool and have the reviewer reassess them; do not silently
migrate their judgments. Review JSON input is bounded to 32 MB, including notes. Review records stay outside
the learner ZIP. See the recipe for commands and review exit codes.

1. Inspect the actual source. Record selected sections, date, claim, and limitations.
2. Write original explanations and tasks; review source fidelity and permissions.
3. Validate and build with the installed `scripts/build_learning.py`.
4. Run the shared reducer tests and representative browser paths before distribution.
5. Increment the topic version for changed published teaching content. Hash binds exact file
   bytes, including source corrections. Older progress is intentionally incompatible;
   open it with the older lesson rather than presenting it as new-version evidence.
   Changes to event-replay semantics also require a topic-version increment, even
   when teaching text is unchanged. Preserve matching old runtime/HTML and exports;
   do not rewrite their identity fields to make them appear compatible. The current
   1.0.2 increment separates this revision from the earlier runtime contract.
6. Release the source pack, self-contained player, compatible skill, and checksums.
   Keep learner exports outside the distribution package.

A local issue export contains only topic ID, version, hash, concept, category, and
report date. It supplies a reproducible lead, not evidence of a teaching improvement.
No auto-promotion loop writes to the pack or skill.

## Compatibility

Player: current Chrome, Edge, Firefox, or Safari with JavaScript and modern DOM APIs.
Offline HTML has no dependency downloads. Browser-local storage on file URLs varies;
explicit JSON export/import is the portable resume path. Browser and OS backups may
retain copies independently of this tool. System time controls review eligibility.

Build: Python 3.11–3.14 with the skill's pinned Python packages. Development reducer
checks: Node.js 22. No Node.js installation is required to use the finished HTML.
The skill and browser lane share concept content; only the browser makes deterministic
selection-score and saved-progress claims. Tutor judgment remains separately labelled.

The browser presents writing criteria before the learner drafts a response and
records writing-example exposure in practice progress. Self-review records the
learner's own checks; it does not grade the written answer. Neither exposure records
nor completed self-checks establish independent application or learner benefit.

## Version 1.0.2 correction

Version 1.0.2 removes ambiguous acceptance alternatives in the obligation review,
adds relevant but insufficient evidence alternatives to timing and intended-use
practice, and explicitly retains an observed use failure alongside a timing pass.
Its final pre-release corrections preserve the cancellation obligation from service
acceptance through display removal, align archiving terminology, explicitly label
the compliance/use misconception and distinguish accessibility support from
corrective destination help in the kiosk example.
Answer keys and source records are unchanged; no new source inspection or human
approval is implied. The [human application rubric](LEARNING_SCORING.md) is now
`requirements-writing-application/1.2`; its scoring clarifications do not establish
scorer reliability. The single-arm feasibility design remains; protocol 1.2 adds
operational timing, assistance, missingness, history de-identification and workload
rules. Those defaults remain pending human freeze, with exact topic/protocol/rubric
versions and hashes recorded together.

Version 1.0.2 is unreleased. Its further pre-release corrections change the topic
hash without changing this version string. Earlier rehearsal receipts for 1.0.2
remain evidence for their prior bytes only; they do not cover the final hash.
Rebuild and repeat affected checks against the final candidate. After publication,
changed teaching content requires another version increment.

Do not import 1.0.0 or 1.0.1 progress into 1.0.2. Keep each older HTML with its exports
to inspect or finish that version. Review worksheets must be regenerated for the
new topic bytes; earlier judgments do not approve this revision.

## Version 1.0.1 correction

Version 1.0.1 distinguished provisional criteria from approved commitments, accepted
adequate measurement and allocation alternatives, and asked for an observable
intended-use success basis. Public questions remain practice. The authoring agent
reinspected the named NASA web sections on 2026-10-03; human acceptance remains
pending. New source dates do not establish historical inspection events.

Do not import 1.0.0 progress into 1.0.1. Keep the old HTML and its exports
together to finish or inspect that version. The published baseline remains
recoverable at Git commit `0223f99c7ab92d34bb92b07abba433dca645393d`; package that
commit in a separate checkout rather than changing version fields in old progress.
