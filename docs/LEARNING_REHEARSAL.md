# Model rehearsal before human review

Date: 2026-10-03. This is development evidence from model simulations and synthetic
browser use. No human participants, human content approvals, protected outcome
forms, or learner-effectiveness results are represented here.

## Independent inputs

Four subagents separately inspected the frozen topic 1.0.1 candidate: one reviewed
all 21 content items and 36 answer choices; one walked through novice, practitioner
and additional-language perspectives; two scored six public synthetic responses
using rubric 1.1 without seeing each other's ratings. Their original ratings and
reports are retained locally in `external-feedback/rehearsal/`.

The two scorers agreed on 28 of 30 criterion ratings. Their totals were respectively
10/3/8/9/7/2 and 10/4/8/8/7/2. This small synthetic comparison located ambiguous
anchors; it does not establish human scoring reliability. Rubric 1.2 clarifies
independent criterion scoring, unresolved-value plans, generic tests, missing
obligation coverage, and treatment of unsupported thresholds. Original ratings are
not retrospectively changed. `evals/public-learning-calibration.json` remains
permanently exposed development material, never reserved outcome evidence.

ChatGPT Pro received an independently frozen 19-file packet via the in-app browser.
Approved packet SHA-256:
`7dd0f7954efbaff834038458b805b76c396f539f37db85b8728ab9d0913bcbbc`.
Its attachment nonce, matching hash and file count were confirmed. The packet
contains topic 1.0.1 and rubric 1.1, so any review conclusions apply to that snapshot;
local follow-up changes require their own verification. The completed review is at
https://chatgpt.com/c/6ac16f7d-c764-83e9-a690-b682a0a24bcd. Complete captured feedback
is retained locally with SHA-256
`4e28c0f2582ed46c742a1efde777564517123d24a2ad660ad30ce9ca4bbb48b1`.
Pro's four perspectives are simulations within one review, not four independent people.

Pro scored the original rubric-1.1 cases 10/3/8/10/8/2. P04's prompt requests
"a feasible verification check", so its omitted record check is ambiguous under
that original contract. Retain that disagreement; do not retroactively impose an
all-obligations rule on the original responses. Rubric 1.2 applies coverage to the
obligations explicitly requested by the task. Human calibration must settle and
freeze the task/rubric pairing before seeing reserved responses.

Pro inspected all 19 embedded files, checked named NASA sections, and reported
20 passing Python tests plus the same 10 Node tests invoked by one Python test.
Two package tests were blocked by omitted packet dependencies, not absent repository
files. It also reported 16 synthetic probes using simulated DOM/storage. Those are
external reports, not local CI results, browser observations or human evidence.
Local deterministic qualification checks the complete repository separately.

## Repairs from the rehearsal

- Record worked-writing-answer exposure as a replay-validated event; distinguish
  assisted writing context from first quiz answers and self-assessment.
- Keep help used during a delayed-review interval visible even after the learner
  revises a draft and repeats its self-review. Regression cases cover study and
  writing examples, and avoid leaking earlier support into a new interval.
- Show writing criteria and permitted alternative approaches before drafting.
- Replace ambiguous pump-question alternatives with actual mistaken conclusions;
  use more relevant measurement and intended-use distractors; retain the observed
  route-guidance failure in feedback.
- Replace navigation, import and clear native confirmations with in-page dialogs
  that focus Cancel, accept Escape, restore focus, and fail without changing work
  if the host cannot show the dialog.

## Pro findings and disposition

| Finding | Local disposition |
| --- | --- |
| Missing writing-example exposure | Confirmed in the frozen callback; explicit replay-validated event and reveal-after-record behavior added. |
| Recent study hidden by repeated self-review | Reproduced; review help window now uses the same initial completion anchor as its due date. Regression tests retain earlier-study exclusion. |
| Shared-tab overwrite and restored cleared data | Reproduced; exact snapshot comparison before writes/removals and storage-event invalidation preserve changed copies. These checks do not make localStorage atomic. One active lesson tab remains the supported rehearsal scope; truly simultaneous writers remain a limitation to resolve before multi-tab support. |
| Save warning overwritten | Reproduced; persistent storage warning survives ordinary feedback until resolved. |
| Event-cap draft/export trap | Confirmed at the reducer limit; separate draft rescue and recorded-history export are implemented, without claiming the draft is replayable progress. |
| ROOM-02 cancellation propagation gap | Confirmed conditional trigger narrows the task; revised public example preserves service-level cancellation responsibility. |
| Pump alternatives and understated route failure | Confirmed; corrected in topic 1.0.2. |
| Archiving wording, misconception metadata, accessibility assistance | Adopted as bounded public-content clarifications; no new reserved questions. |
| Scoring differences and coverage ambiguity | Preserved original ratings; clarified draft anchors without promoting any model score to a gold standard. |
| Timing, workload, rubric-visible outcomes, assistance and missingness | Adopted into the draft operational protocol; final human freeze remains required. |
| Historical drafts in exports | Confirmed by write-event replay; de-identification must inspect all transferred history or use separately prepared scoring artifacts. |
| Native dialog cause | Unresolved; in-page confirmations are a portability change, not proof of the original cause. |
| Full package not reproducible from Pro packet | Packet-scope limitation; local package validation uses the actual complete repository. |
| Novice terminology, duration and interval effectiveness | Hypotheses for human observation; no measured benefit or optimal schedule asserted. |
| Import timing races | Advisory test request, not an established defect; tested locally during repair. |
| Device and human sign-offs | Remain explicit gates in the acceptance record and run sheet. |

## Human handoff boundaries

Topic 1.0.2 requires a fresh exact-byte worksheet with all 21 decisions pending.
No model report may fill those human decisions. The candidate still needs an
independent source/answer-key reviewer, two human scorers, a data custodian,
consent/retention arrangements, reserved forms outside the repository, and an
owner-approved pilot freeze. The protocol remains single-arm feasibility, not an
efficacy experiment. Actual target-device accessibility and browser compatibility
checks remain in `LEARNING_ACCEPTANCE.md` and the run sheet.
