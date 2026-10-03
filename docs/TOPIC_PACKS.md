# Topic packs and distribution

The first pack is `requirements-writing` version `1.0.0`, in the installed skill's
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
5. Increment the topic version for changed teaching content. Hash binds exact file
   bytes, including source corrections. Older progress is intentionally incompatible;
   open it with the older lesson rather than presenting it as new-version evidence.
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
