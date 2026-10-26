# User-Controlled Profiles and Decision Fit Scoring

The [shared record contract](../record-store-contract.md) governs operations. The calculator produces inspectable session-only arithmetic, not a persisted dossier or a qualified host. Do not coerce this content into a growth-record schema that cannot represent it. Use a requested portable card when unsupported; never fabricate save, correction or deletion.

Use this reference when the user asks to create, update, compare, score, review,
remember, correct, export, roll back, or delete a profile about themselves,
another person, a relationship, a stakeholder, or an interpersonal option.

The product supports optional dossiers and numerical scoring. Start with a
session-only evidence table; do not introduce a score merely to make advice look
precise. This reference defines optional interpersonal case content under
[shared continuity](../memory-and-continuity.md) and the shared record contract;
it does not override them. [Case continuity](memory-and-continuity.md) adds
content minimization, freshness and correction rules. Another person's evidence
belongs only within the user's bounded decision, not a standalone person dossier
or a profile aggregated across unrelated cases. No separate persistent case schema
or adapter is supplied. Persistent case content needs an actual supported host
representation and the shared consent/attestation controls; otherwise keep it
session-only and offer a requested unsaved portable card.
Hidden, fixed, diagnostic, vulnerability, or manipulation profiles remain prohibited.

## Render uncertainty before arithmetic

Calculator output schema 1.1 accepts legacy 1.0 inputs, but intentionally changes
headline-score behavior. Every positive-weight dimension defaults to
`decision_critical: true` unless the user explicitly marks it otherwise.
Unresolved unknowns in a critical dimension block an overall assessment even
when someone supplied a rating. An active flag always takes precedence.

Keep missing evidence distinct from active flags: with rated evidence, critical
unknowns produce `insufficient_evidence`; no rated evidence produces
`not_calculable`; `gated` requires an actual active flag. Do not turn an
unknown authority into an established authority breach. Without a supplied model
and an executed calculator result, explain the applicable condition rather than
presenting an invented status as a returned calculation.

Render `decision_status`, `interpretation`, coverage, critical unknowns, and
flags first. `decision_fit_score` is null while gated, unassessed, or incomplete.
`arithmetic_only.scored_dimensions_score` may be shown as partial arithmetic,
never a favorable overall verdict. `full_model_bounds` spans the user model when
unknown ratings range from 0 to 5; it is not a probability or confidence interval.
Do not impute the unknown ratings or lower weights to obtain a reassuring score.

For example, one 5/5 dimension among eight equally weighted dimensions yields
12.5% coverage, a null headline score, and sensitivity bounds of 12.5–100.
An active safety flag still blocks a favorable verdict if every rating is 5/5.
Show the evidence and next information need instead of rating the person.

## Start with user control

Before creating or materially expanding a persistent dossier, establish:

- the user's decision or support purpose;
- the actor or relationship scope;
- whether the record is session-only or persistent;
- an alias or role to use;
- the minimum source material needed;
- sensitive fields that must not be retained;
- the first review or expiry event.

Do not silently create a profile, infer that persistence is wanted, or claim a
write succeeded unless the host confirms it. If the host has no persistence,
offer the dossier as a copyable block and say that it has not been saved.

Honor `memory off` immediately. With memory off, the current response may use
provided context but must not write, update, or broaden a dossier.

## Keep three records distinct

### User profile

Record the user's own confirmed information:

- goal, priorities, values, boundaries, and deal-breakers;
- communication preferences and accessibility needs;
- resources, dependencies, deadlines, and downside exposure;
- relationship history needed for the current decision;
- optional self-descriptions such as Big Five or MBTI, marked `user-supplied`;
- preferred score dimensions and weights.

### Counterpart decision context

Within the user's case, keep only decision-relevant evidence about the other
person, using an alias or role. This supports the user's choices, not a person
profile independent of that decision:

- role or alias and relationship to the user;
- their directly stated preferences, boundaries, decisions, and commitments;
- dated observable behavior and material patterns;
- interpretations labeled as hypotheses;
- counterevidence, contradictions, and unknowns;
- current access, authority, dependency, and contact constraints;
- source, freshness, confidence, and next update condition.

Do not add a vulnerability, pressure-point, sexual-preference, medical,
credential, secret-location, surveillance, or manipulation field. Do not infer
personality, diagnosis, attachment, MBTI, attraction, honesty, or consent from
photos, avatars, body movement, voice, punctuation, emoji, or response time.

### Relationship or decision record

Record the shared context without collapsing the two people:

- relationship type as the user describes it;
- current state and decision to make;
- timeline of material events;
- agreements, commitments, refusals, boundaries, and open loops;
- support, burden, reciprocity, conflict, repair, and trust evidence;
- power, money, housing, work, caregiving, reputation, and safety exposure;
- options, score snapshots, selected action, review point, and stop conditions.

In multi-actor cases, distinguish each actor's evidence within the case. Do not
merge one person's statement, motive hypothesis, score, or boundary with another's,
or create separate reusable dossiers about non-users.

## Use an evidence-labeled dossier schema

```markdown
# Interpersonal decision case: [bounded user decision]

Case ID: [opaque host-issued identifier, or not saved]
Version: [number]
Created: [date]
Last updated: [date]
Review or expiry: [date or event]
Mode: session-only | persistent only with verified supported host representation
Purpose: [decision this supports]
Scope: [people and relationship context]
Sensitive exclusions: [what must not be stored]

## User priorities
- [confirmed priority, weight, source/date]

## Counterpart and context
- Fact/report: [content, source/date]
- Observation: [content, source/date]
- Hypothesis: [content, evidence, counterevidence, confidence, update condition]
- Unknown: [question and materiality]

## Relationship timeline and commitments
- [date, event, source, status]

## Decision Fit Score snapshot
- Purpose and dimensions: [...]
- decision_status: [actual calculator status]
- Interpretation: [decision limit and next information need]
- Active flags: [none or the actual flags]
- Critical unknowns: [missing decision-critical evidence]
- Coverage: [percentage and dimensions missing]
- Confidence: low | moderate | high
- decision_fit_score: [null if gated, unassessed or incomplete; otherwise 0-100]
- Partial arithmetic, if useful: [arithmetic_only.scored_dimensions_score]
- Sensitivity bounds, if useful: [full_model_bounds; not a confidence interval]

## Current strategy
- Recommendation: [...]
- Branches: [...]
- Review point: [...]
- Stop condition: [...]

## Correction history
- [date, prior entry, correction, source, affected score/version]
```

Use plain Markdown or an equivalent inspectable host format. Do not hide a
parallel internal profile from the user.

## Separate evidence classes

Label each material entry:

- **confirmed fact:** directly established and attributable;
- **counterpart statement:** what the person explicitly said or wrote;
- **user report:** what the user recalls or reports;
- **observation:** behavior or event described without motive;
- **hypothesis:** interpretation that may be wrong;
- **counterevidence:** evidence against the leading interpretation;
- **unknown:** missing information that could change the decision.

For raw messages or records, retain a compact paraphrase and source pointer when
possible. Do not retain full private transcripts, intimate images, credentials,
or unnecessary identifiers merely because they were provided for analysis.

## Build a Decision Fit Score

The **Decision Fit Score (DFS)** is a custom 0–100 summary of the user's stated
decision model. It is not a validated psychological test, compatibility
instrument, diagnosis, consent determination, or prediction of success.

### Step 1: name the decision

Score a bounded question, not a human being.

Good:

- How well does continuing this friendship fit my current needs and evidence?
- How viable is relying on this colleague for this deliverable?
- How well does pursuing an exclusive partnership fit our stated goals now?
- Which of two conflict-repair options is stronger under my priorities?

Bad:

- What is this person's objective value?
- How loyal, attractive, truthful, or controllable are they?
- What is the probability they will consent, return, cheat, or change?

### Step 2: select dimensions

Use four to eight decision-relevant dimensions. The default library is:

| Dimension | What to assess |
|---|---|
| Goal and values fit | Compatibility of directly stated aims, standards, and non-negotiables for this decision |
| Reciprocity and burden | Balance of contribution, care, initiative, cost, and benefit over a relevant window |
| Responsiveness and care | Observable understanding, validation, support fit, and attention to material needs |
| Clarity and truthfulness | Directness of statements, correction of errors, consistency with records, and unresolved ambiguity; not lie detection |
| Reliability and follow-through | Commitments, delivery, repair after misses, and predictability under comparable conditions |
| Boundary and consent respect | Response to limits, refusals, privacy, choice, and current voluntary agreement |
| Conflict and repair capacity | Ability to address impact, lower escalation, remedy harm, change controls, and review behavior |
| Sustainability and constraints | Time, energy, distance, money, power, caregiving, work, health, or other practical conditions the user disclosed |

Optional modules may add user-rated attraction, intimacy satisfaction, role
authority, access, collaboration quality, family fit, or another construct that
materially changes the decision. User-rated attraction or intimacy is the
user's subjective experience; never infer the other person's attraction or
consent and never request intimate media to score it.

### Step 3: anchor every dimension

Use a 0–5 rating with dimension-specific evidence:

| Rating | General anchor |
|---:|---|
| 0 | Directly blocked, repeatedly contradicted, unsafe, or incompatible for this decision |
| 1 | Strong unfavorable evidence with little credible offset |
| 2 | More unfavorable than favorable; substantial condition or repair needed |
| 3 | Mixed or workable with explicit conditions and unresolved evidence |
| 4 | Strong favorable evidence with manageable limitations |
| 5 | Consistent favorable evidence across relevant situations and time |
| unknown | Evidence is insufficient; do not substitute 2.5 or zero |

For each rating record:

- dimension definition;
- user-selected weight from 0 to 3;
- rating and anchor;
- supporting evidence and source/date;
- counterevidence;
- material unknowns;
- confidence: low, moderate, or high;
- update condition.

### Step 4: calculate status before optional arithmetic

Use the schema 1.1 status-first contract above. Positive-weight dimensions with
unknown ratings remain in planned coverage. Missing decision-critical evidence
(including unresolved material unknowns on a rated dimension) prevents an overall
score. Any active safety, consent, authority, or deal-breaker flag gates it first.

```text
partial arithmetic = 20 × sum(scored weight × rating) / sum(scored weight)
coverage = scored planned weight / total planned weight × 100
lower sensitivity bound = 20 × sum(scored weight × rating) / total planned weight
upper sensitivity bound = 20 × (sum(scored weight × rating) + 5 × missing weight)
                          / total planned weight
```

These bounds only vary missing ratings over their declared 0–5 range. They do
not represent probability, measurement error, or uncertainty in the supplied
ratings. Keep confidence and counterevidence visible. No universal favorable
interpretation bands are supported. Even complete arithmetic is not a
recommendation and does not validate the user's chosen dimensions or weights.

For deterministic arithmetic, copy `assets/profile-score-template.json`, retain
source/date on evidence, and run `scripts/profile_score.py --input <model.json>`.
Render `decision_status`, `interpretation`, missing critical evidence, and flags
before `arithmetic_only`. Never turn partial arithmetic into an overall headline.
The helper does not infer ratings or write memory. Use `--output` only when the
user explicitly chooses a destination. A saved output file is not host memory.

### Step 5: report confidence separately

Confidence describes the evidence basis, not decimal precision:

- **low:** sparse, stale, one-sided, contradictory, or mostly inferential;
- **moderate:** several relevant observations with some corroboration and open
  uncertainty;
- **high:** repeated recent behavior or explicit records across relevant
  contexts with little material contradiction.

Do not report invented probabilities or decimal confidence. If the score moves
because the user changed weights rather than because evidence changed, say so.

### Step 6: preserve gates outside the average

Do not average away:

- a user deal-breaker;
- a clear refusal or withdrawn consent;
- violence, threats, coercion, stalking, or exploitation;
- adult-minor sexual or romantic content or inability to consent;
- a binding authority, policy, legal, or safeguarding constraint;
- a material privacy or retaliation risk.

Show these as separate flags. Route safety and qualified-referral cases before
score interpretation.

## Compare people or options carefully

Use the same decision, dimensions, anchors, evidence window, and weight set for
each option. Show each score's coverage and confidence. Do not force a ranking
when one option has materially poorer data or a different relationship context.

When comparing people, state:

- this is fit for the user's bounded decision, not comparative human worth;
- each person has a separate evidence record;
- a higher score can still lose if it violates a deal-breaker or safety gate;
- the user may choose an option for reasons not represented in the model.

## Correct, version, expire, and delete

### Correction

When the user says an entry is wrong:

1. acknowledge the correction without treating it as resistance;
2. identify the affected fact, hypothesis, score, or source;
3. preserve the prior value in correction history unless the user requests
   deletion;
4. update dependent dimensions;
5. show which score change came from evidence, weights, or both;
6. create a new version for a material decision change.

### Version and rollback

Create a snapshot when the decision, people, weight model, material evidence,
recommendation, or safety status changes. Preserve version, date, change note,
and prior score. Rollback restores an earlier active view but does not erase the
fact that a rollback occurred.

### Expiry and freshness

Every hypothesis and score needs a review date or observable update event.
Mark a score stale when the decision, relationship state, evidence window, or
material constraints change. Do not silently carry a score into a new context.

### Deletion and export

On request, show the record, export it in an inspectable form, or delete the
specified profile. Confirm the exact target before deletion and report what the
host actually removed. Do not claim deletion from backups or external systems
the host cannot verify.

## Refuse misuse while preserving legitimate scoring

Refuse or redirect when the requested profile or score is for:

- exploitation, pressure, grooming, retaliation, surveillance, or stalking;
- identifying vulnerabilities, pressure points, or the best manipulation tactic;
- predicting consent, deception, diagnosis, criminality, or protected-trait
  behavior;
- secret recording, credential access, intimate-media analysis, or unauthorized
  third-party data collection;
- consequential formal decisions that require a validated instrument or
  qualified professional.

Offer a safe alternative: score the user's options, relationship fit, reliance,
exposure, or observable pattern using minimized evidence and explicit controls.

## Compact output

For ordinary use, return:

1. the score question;
2. decision_status and its interpretation, active flags, critical unknowns,
   coverage and evidence confidence before arithmetic;
3. a dimension table with weights, ratings, evidence and unknowns;
4. decision_fit_score, explicitly null when gated, unassessed or incomplete;
   label any arithmetic_only.scored_dimensions_score and full_model_bounds as
   partial arithmetic and sensitivity bounds, never an overall verdict;
5. a useful action or non-action, update condition and review event;
6. a case-record delta only when requested under the shared continuity contract.

Use the same status-first order in a requested dossier or comparison. Do not
lower weights, erase unknowns or hide flags to obtain a headline score.

Do not dump the full dossier unless the user asks to inspect it or the detailed
record is needed for correction.

## Evidence boundary

Relationship research supports several dimensions as relevant review prompts.
Measurement standards support clear constructs, intended uses, limitations,
and user rights. Neither validates this product's weights, bands, or composite
as a predictive instrument. See `RELATION-02` through `RELATION-08`,
`MEASURE-01`, `MEASURE-02`, `CONSENT-01`, `CONSENT-02`, `SAFETY-01`,
`SAFETY-02`, and `PERSONALITY-01` in the evidence ledger.
