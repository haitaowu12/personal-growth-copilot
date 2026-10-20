# Requirements-writing feasibility protocol

Protocol: `requirements-writing-feasibility/1.2`. Topic: `requirements-writing@1.0.2`.
Scoring rubric: `requirements-writing-application/1.2`.
Status: draft protocol; recruitment is blocked until the human
sign-offs and candidate-specific rehearsal below are recorded. No participants,
outcomes, human approvals or efficacy results are claimed.

Protocol 1.2 retains the single-arm feasibility design and adds draft operational
rules for timing, assistance, missingness, data handling and workload. Topic 1.0.2
clarifies public examples and alternatives; rubric 1.2 clarifies scoring anchors.
Freeze the exact candidate, protocol and rubric together. Historical protocol 1.1,
topic 1.0.1 or rubric 1.1 records do not establish approval of this combination;
retain original versions and ratings when documenting later clarifications.
All operational defaults below remain pending human review and freeze.

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
The custodian must check that each form elicits every criterion; counterbalancing
does not establish equivalent difficulty. No protected form is supplied here.

## Session sequence

1. Obtain consent and a pseudonymous ID. Record prior requirements-writing
   experience, domain knowledge, language familiarity and chosen accommodations.
2. Show the public rubric and collect the reserved baseline task without conceptual
   assistance. The draft allowance is 20 active minutes per outcome task, with
   stopping permitted at any time. Retain unfinished work. Do not release scored
   feedback before delayed assessment.
3. Offer a learning session with a target of 20 active minutes in the offline player.
   This is an estimate, not a validated duration or the total appointment time.
   Record active time, elapsed time, breaks, early stopping, navigation friction,
   source access, hints, example use, repetitions and substantive human help.
   Writing criteria appear before drafting. The player records writing-example
   exposure in practice progress; retain that exposure when describing assistance.
   Completed self-review is the learner's own judgment, not a grade of the answer.
   Record the actual route: completing all concepts does not mean every explanation
   was studied, every self-check was positive, or writing skill was demonstrated.
4. Close the lesson and collect the reserved immediate task. Keep the same public
   rubric visible at all three timepoints. The outcome is **rubric-visible unassisted
   application**, not unsupported recall. No lesson, sources, prior answer,
   AI, examples or conceptual hints are available during an unassisted outcome.
5. Invite the delayed task at 168 elapsed hours after the **learning-session end**
   recorded in step 3. The task must start in the inclusive 6–9-day window:
   **144 ≤ elapsed hours ≤ 216**. Record learning end, delayed start and delayed end
   with time zone/UTC offset; classify the window by task start, not submission time
   or calendar-date labels. Retain early starts below 144 hours and late starts above
   216 hours with separate outside-window flags. Record intervening learning.
   Administer the task **before** opening the player's day-seven review, revisiting
   lesson explanations, or supplying outcome feedback. This order is administered
   by the facilitator; the player does not enforce a study lock. Intervening review
   is exposure; conceptual help during the task is assistance. Retain both flags
   when both occur, independently of the timing classification.
6. After the delayed task, allow lesson review and debriefing. Ask about effort,
   confidence, useful aspects and confusing feedback. Do not promise competence.

For each phase, record start/end, wall-clock elapsed minutes, active minutes, each
pause/break and reason, and early stopping. Active time excludes recorded pauses;
elapsed time includes them. Prespecify accommodations and any additional allowance
at freeze, use them consistently, and retain actual durations rather than silently
truncating work to the planned allowance.

Record assistance in distinct categories: neutral procedural help; literal reading
or motor assistance; translation; conceptual explanation or answer suggestion; and
uncertain assistance. Screen reading, enlarged text, breaks and motor assistance
that add no conceptual answer are accommodations, not conceptual help. Translation
needs a prespecified approach checked for conceptual additions; otherwise mark it
uncertain. Uncertain cases remain flagged and outside the unassisted summary until
adjudicated with a recorded reason; never default them to unassisted.

Use authorized facilitator/participant reports alongside player exposure records.
A source click does not prove reading, and no recorded click does not establish
absence of outside exposure. Exposure beyond the planned lesson and public rubric,
assistance, and early/late timing are independent, potentially overlapping flags.

## Scoring and reporting

The primary descriptive measures are immediate and delayed rubric-visible unassisted application
quality on five 0–2 criteria, totaling **0–10**. Report each criterion as well as the
total; baseline is context, not a causal control. Earlier protocol 0–8 scores omit
purpose and must not be pooled or rescaled into this series. Report the delayed
in-window, unassisted, unexposed subset explicitly; retain other flagged observations
as separate descriptive strata without implying that the flags are mutually exclusive.

Two human scorers calibrate on public practice examples, not reserved tasks. The
custodian removes participant identifiers and player/condition labels, randomizes
artifact order and conceals timepoint where feasible; record any unavoidable
unblinding. Retain both original ratings,
criterion-level agreement/disagreement and adjudicated scores with reasons. Small
sample agreement is a feasibility observation, not validated scorer reliability.

An assessable attempt contains a substantive response to at least one requested
requirement or check, even if incorrect. An unfinished but assessable artifact is
scored on the evidence present; an omitted criterion can receive zero only when
the task actually elicited that dimension. An absent artifact, blank submission,
refusal, or administrative text without a substantive attempt has no application
score. Distinguish missing artifacts from received nonresponses and record reasons
when volunteered. Do not assign an artifact-level zero to either category.

Report all enrolled learners, withdrawals, assessable complete/incomplete artifacts,
nonresponses, missing baseline/immediate/delayed work, assisted/exposed work and
outside-window follow-ups. Missing work is missing, not zero and not success.
Give the enrolled denominator and the received, assessable and analysis-subset
denominators at each timepoint. Counts for overlapping flags need not sum to the
participant total; also report their intersections. Use descriptive distributions;
do not substitute more favorable quiz scores or self-checks for application scores.
Secondary observations: time, assistance, confidence versus work, misconceptions,
friction, effort and follow-up practicality. No automated grading is introduced.

## Draft operational budget

These are planning allowances, not measured workload or human commitments. Before
recruitment, the owners must accept or replace them and freeze the resulting budget.
Plan 90 minutes for the initial appointment: consent/context 10, setup 5, baseline
20, scheduled breaks 10, learning 20, immediate task 20 and closeout 5. Plan 35
minutes for delayed contact: setup 5, task 20 and debrief 10. Thus planned participant
contact is 125 minutes each, excluding additional agreed accommodations/breaks.
The learning target of 20 minutes is only one part of that appointment.

For 6–10 participants with three assessable timepoints each, plan 18–30 artifacts,
36–60 independent rating sets from two scorers, and 180–300 criterion judgments
before adjudication. Use the following role budget in person-hours:

| Role/work | Draft arithmetic | 6–10 participants |
| --- | --- | --- |
| Facilitator contact and per-person administration | (125 contact + 15 administration) minutes × participants ÷ 60 | 14–23.3 hours |
| Custodian preparation and artifact handling | 2 fixed hours + 30 minutes × participants ÷ 60 | 5–7 hours |
| Two scorers: independent ratings and calibration | 15 minutes × 3 artifacts × participants × 2 scorers ÷ 60 + 1 calibration hour × 2 scorers | 11–17 hours |
| Joint adjudication contingency, if every artifact needs it | 5 minutes × 3 artifacts × participants × 2 scorers ÷ 60 | 3–5 hours |
| Total planned role effort | Sum of the above, without double-counting shared appointments | 33–52.3 person-hours |

Role overlap does not remove required independent ratings. This budget excludes
recruitment, human content/source review, protected-form development/review, travel,
unexpected remediation and extra accommodations; owners must add those allowances
and confirm staffing. Log actual workload by role, including incomplete timepoints.

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
Progress exports retain historical saved write events, not just the latest draft.
Removing an identifier from the visible answer does not sanitize earlier text.
Create separate, minimized scoring artifacts under the custodian's authority.
If a transfer of history is necessary and authorized, inspect and de-identify every
historical write, other free-text field and identifying metadata in that transfer.
Keep any derivative labelled as such, separate from the original replay record;
do not present edited exports as unchanged authenticated progress. Preserve the
source record only under the agreed access and retention rules.
Keep the participant identity key separately under the custodian's control. Record
withdrawal handling without pressuring the learner to finish. Clearing the browser
cannot delete downloaded files, sent copies or backups; disclose and handle them
under the agreed retention plan. No learner data is sent to model services by this
protocol. Recruitment, reminders and external transfers require their own authority.
