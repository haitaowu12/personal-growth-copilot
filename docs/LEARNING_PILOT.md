# Requirements-writing feasibility protocol

Protocol: `requirements-writing-feasibility/1.1`. Topic: `requirements-writing@1.0.1`.
Status: implementation-ready protocol; recruitment is blocked until the human
sign-offs and candidate-specific rehearsal below are recorded. No participants,
outcomes, human approvals or efficacy results are claimed.

## Scope and question

Use the offline player, with all three concepts: clear obligation, observable
acceptance boundary, and intended-use reasoning. The first study is single-arm
feasibility with 6–10 consenting adults. Can participants complete the workflow,
produce assessable work, and return for delayed assessment? Describe performance
and friction; do not attribute improvement causally to the player.

Conversational tutoring is outside this intervention. There is no source-reading
comparison or crossover in this protocol. A comparative study needs its own frozen
allocation, matched materials and analysis plan after feasibility. Six to ten
participants cannot establish efficacy, mastery or optimal spacing.

## Freeze before recruitment

Complete the [run sheet](LEARNING_PILOT_RUN_SHEET.md): commit, topic/player/package
hashes, protocol/rubric version, device/browser scope, human content approval,
source/reuse disposition, two scorers, outcome custodian, consent and retention
terms, reserved-task identifiers and analysis plan. No unexplained blanks may be
treated as approval. The current candidate has no independent human acceptance.

The independent custodian maintains three distinct, unexposed task forms for
baseline, immediate and delayed performance. Each must permit scoring all five
criteria in the [public rubric](LEARNING_SCORING.md), using invented project facts.
Counterbalance task-form order across participants, recording allocation before
exposure; this balances forms, not teaching effects. Keep questions, model answers,
scoring keys and exposure records outside the implementation repository and model
tuning conversations. Once used for tuning, a form is no longer untouched.

## Session sequence

1. Obtain consent and a pseudonymous ID. Record prior requirements-writing
   experience, domain knowledge, language familiarity and chosen accommodations.
2. Show the public rubric and collect the reserved baseline task without conceptual
   assistance. Record elapsed time, attempted work and any help rather than forcing
   completion. Do not release scored feedback before delayed assessment.
3. Offer a 20-minute learning session in the offline player. This is an estimate,
   not a validated duration. Record actual time, early stopping, navigation friction,
   source access, hints, example use, repetitions and substantive human help.
4. Close the lesson and collect the reserved immediate task. The public rubric may
   remain visible, identically at every timepoint. No lesson, sources, prior answer,
   AI, examples or conceptual hints are available during an unassisted outcome.
5. Invite a delayed task at seven days, with a prespecified 6–9-day window. Record
   actual elapsed hours and intervening learning. Administer it **before** opening
   the player's day-seven review or supplying any outcome feedback. An early lesson
   review or substantive help flags that outcome as exposed/assisted; retain it
   separately. Late work is retained and labelled outside-window.
6. After the delayed task, allow lesson review and debriefing. Ask about effort,
   confidence, useful aspects and confusing feedback. Do not promise competence.

An accommodation such as screen reading, enlarged text, a break or motor assistance
that adds no conceptual answer is not conceptual help. Record its nature and use
consistently where practical. Resolve ambiguous assistance before scoring; report
assisted outcomes separately, never silently relabel them unassisted.

## Scoring and reporting

The primary descriptive measures are immediate and delayed unassisted application
quality on five 0–2 criteria, totaling **0–10**. Report each criterion as well as the
total; baseline is context, not a causal control. Earlier protocol 0–8 scores omit
purpose and must not be pooled or rescaled into this series.

Two human scorers calibrate on public practice examples, not reserved tasks. The
custodian removes participant identifiers and player/condition labels, randomizes
artifact order and conceals timepoint where feasible. Retain both original ratings,
criterion-level agreement/disagreement and adjudicated scores with reasons. Small
sample agreement is a feasibility observation, not validated scorer reliability.

Report all enrolled learners, withdrawals, missing baseline/immediate/delayed work,
assisted/exposed work and outside-window follow-ups. Missing work is missing, not
zero and not success. Use descriptive distributions and counts with denominators;
do not substitute more favorable quiz scores or self-checks for application scores.
Secondary observations: time, assistance, confidence versus work, misconceptions,
friction, effort and follow-up practicality. No automated grading is introduced.

## Rehearsal and decision gates

Before inviting learners, use synthetic public practice to rehearse consent,
timing, accommodation handling, exports, de-identification, scoring and withdrawal.
The named pilot devices must pass the actual candidate's keyboard, narrow-view,
save/resume/export/import/clear and unsaved-draft paths. Test storage-denial handling;
record simulated failures separately from real device evidence. Historical browser
receipts do not establish the current candidate's behavior.

Block on misleading feedback, lost unsaved work without warning, unauthorized
storage, content injection, unexplained network behavior, contaminated reserved
forms, absent owners/consent, or unreviewed content. After feasibility, resolve
critical issues and decide which next question the retained evidence supports.
A successful feasibility run does not promote the wider coaching product.

## Data handling

Device saving is off by default; learners choose exports. No telemetry or automatic
collection is added. Consent must name who receives written artifacts, purpose,
retention period, storage location, withdrawal deadline and contact, and deletion
limits. Use invented scenarios; de-identify before any separately authorized transfer.
Keep the participant identity key separately under the custodian's control. Record
withdrawal handling without pressuring the learner to finish. Clearing the browser
cannot delete downloaded files, sent copies or backups; disclose and handle them
under the agreed retention plan. No learner data is sent to model services by this
protocol. Recruitment, reminders and external transfers require their own authority.
