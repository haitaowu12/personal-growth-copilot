# Public application scoring rubric

Version: `requirements-writing-application/1.2`. Five criteria, each 0–2; total 0–10.
Purpose: descriptive human scoring for the all-concept feasibility protocol.
This is not an automated grader, engineering approval or a mastery threshold.
These clarifications do not establish validated scoring reliability.

| Criterion | 0: absent or incorrect | 1: partial | 2: sufficient for the stated task |
| --- | --- | --- | --- |
| Responsible product | No responsible product, or only a person's intention | Product implied or inconsistently named | Product/system is explicit and consistently responsible for the required behavior |
| Independent obligation | Combines independently failing outcomes without distinction | Main obligation identifiable but one outcome remains entangled | Each relevant obligation is independently checkable; allocation can differ from the worked example when justified |
| Conditions, result and acceptance basis | No observable result, or an invented limit presented as an approved promise | Observable result is present, but some relevant trigger/condition/boundary information or its basis is missing or unclear | Relevant trigger/conditions, observable result and boundary are explicit with a defensible stated basis; justified provisional/open values are clearly marked with rationale, owner, resolution action and date or named review milestone when the task leaves them unresolved |
| Verification evidence | No observable link to a stated requirement, including a generic instruction to run a test | A relevant check has a weak link to trigger, result or acceptance decision, or adequate checks cover some but not all requested obligations | Feasible observations/analyses compare required results with their criteria under relevant conditions for all requested obligations; equivalent adequate measurement methods count |
| Intended-use reasoning | Equates compliance with usefulness, or supplies no use check | Recognizes the distinction but misses outcome, representative context or success basis | Preserves the bounded compliance claim and states an intended-use outcome, relevant users/conditions and observable success basis; evidence may overlap with verification |

Score the evidence in the response, not eloquence, length or similarity to the
example. Score each criterion independently: an explicit, consistently named
responsible product can receive 2 even when its outcomes are vague. Record those
defects under the criteria they affect; do not propagate a low score automatically.

A provisional criterion is not an approved baseline. When the task explicitly
leaves a value unresolved, acknowledging that status supplies the rationale for
keeping it open; do not require an invented explanation for the missing decision.
The response must still identify an accountable owner, a resolution action and a
date or named review milestone. For example, a service-owner decision on format
and retention before the design review is a resolution plan. A named review is
adequate when it is an identifiable decision point and the response says when the
action must occur relative to it; a calendar date is not additionally required.
"Resolve later" is insufficient. A proposed value needs a stated rationale for
that proposal and must remain explicitly subject to resolution or agreement.

Do not invent missing facts for a participant. A supplied scenario limit must not
be silently replaced: an invented limit stated as the requirement's approved
promise scores 0 for conditions/result/basis. Otherwise, use 1 when an observable
result is present but a relevant component or basis is incomplete, recording what
is missing; use 2 only when the stated full-credit conditions are met. An
acknowledged task-supplied unknown with an adequate resolution plan is not itself
a reason to reduce the score.

Judge verification against the obligations the task requests the participant to
check. A bare "run a test" scores 0. A sufficient timing check with no check of a
separately requested recording obligation scores 1. Full credit requires adequate
checks for both; it does not require testing unresolved format or retention values
as though already approved. An incorrect threshold is penalized under
conditions/result/basis and flagged in verification notes. By default, judge the
verification method separately: an adequate observation and comparison against
the written threshold does not receive another deduction solely because that
threshold is unsupported. Missing observations, conditions or obligation coverage
can still reduce the verification score independently.

If a reserved task cannot elicit all five criteria, repair it before freeze; do not
award arbitrary zeroes for an unasked dimension.

Accept system-level or component-level allocations that satisfy the task, and
adequate elapsed-time methods besides timestamp subtraction. Verification and
validation can use the same trial while evaluating different objectives. Merely
watching a user, counting requirements or passing a timing threshold is not a
complete intended-use argument.

Use the published lesson examples for scorer calibration. Record each original
rating and its rationale, discuss discrepancies, then freeze anchors before seeing
reserved responses. Do not create or publish reserved assessment questions here.
Public calibration cases, including synthetic model rehearsals, remain permanently
exposed development material. They cannot become held-out outcome evidence.
Model rehearsal scores are not human ratings, learner evidence or evidence of
scoring reliability; retain original ratings when documenting later clarifications.
A score is descriptive: no pass/fail or competence cutoff is defined by this rubric.
