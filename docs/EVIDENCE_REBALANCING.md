# Evidence rebalancing candidate slice

Date: 2026-08-13
Parent candidate: `codex/qualification-packet-bootstrap` at
`767fa96ca51116f916997d04a8cf3cff67ee9515`
Status: candidate design assets; release remains blocked

## Purpose

The repository already has stronger release-evidence integrity controls than
behavioral or user-outcome evidence. This slice does not add another promotion
mechanism. It adds inspectable design assets needed to test whether the product
helps with ordinary personal-growth work, at what burden, and with what limits.

## Added assets

### Governed technique registry

`skill/personal-growth-copilot/assets/technique-registry.json` maps each
candidate intervention ingredient to:

- a Behaviour Change Intervention Ontology identifier;
- the barrier it may address;
- eligibility conditions;
- contraindications and minimum burden;
- an expected proximal signal;
- a disconfirming signal and review window;
- alternatives and evidence-source IDs.

The registry is a selection and falsification aid. Ontology membership does not
establish effectiveness. The model may use only a technique whose eligibility
conditions fit user-provided evidence; the user can reject it.

### Explicit-save session capsule

`skill/personal-growth-copilot/assets/session-capsule.schema.json` defines a
human-readable continuity artifact adapted clean-room from community session
formats. It preserves user wording, facts, hypotheses, alternatives,
disconfirmers, the user's choice, optional experiment, review points, open
questions, and exact persistence status.

The capsule is prepared only when requested. It is not automatically loaded or
stored, does not replace the growth-record consent contract, and cannot claim a
write without a host receipt.

### Ordinary-growth and longitudinal candidate suite

`evals/ordinary-growth-cases.json` adds authored cases for career decisions,
learning, environmental constraints, failed hypotheses, outcome bias,
intentional non-action, directness, stale memory, metric burden, Chinese family
pressure, recovery, and capacity transfer. Each case specifies:

- a primary user outcome;
- a question and unrequested-growth-move burden budget;
- required and forbidden process observations;
- a delayed review event where material;
- strong comparator systems.

These cases are deliberately separate from the canonical governed execution
suite. They become behavioral evidence only after Codex integrates them into a
frozen run plan, verifies schema parity, preserves all attempts, and obtains the
required human labels.

### Strong comparator contracts

The candidate comparators prevent a straw-baseline result:

- `strong_generalist`: same model, safety policy, and context access without the
  PGC method;
- `mi_informed`: non-clinical reflective conversation without a dossier;
- `session_capsule`: direct assistance plus an explicit-save summary without
  adaptive longitudinal modeling.

The existing direct and structured-reflection comparators remain useful as
ablations. Any claimed PGC benefit must account for turns, disclosure burden,
time-to-action, and user authorship.

### Evidence and community supplements

The supplements add current source fields for population, comparator, duration,
outcomes, risk, directness, disposition, maintenance, adoption, licensing, and
known limitations. Conflicting randomized coaching results remain visible;
neither is converted into a product efficacy claim.

## Evidence model

Evaluation should report five separate classes:

1. **Process:** correction, material inquiry, evidence separation, and fit.
2. **Proximal user outcome:** clarity, user-authored choice, feasible next step,
   and a falsifiable observation.
3. **Delayed outcome:** attempt, non-attempt, dropout, changed model, and method
   transfer at the agreed review event.
4. **Burden:** turns, questions, disclosure, tracking, and elapsed time.
5. **Dependence and displacement:** stopping behavior, real-world action, human
   support, and whether the user feels less able to decide independently.

No aggregate score may waive safety, privacy, dependence, fabricated resource,
or fabricated persistence failures.

## Deliberate non-changes

This slice does not:

- install or register the skill;
- enable implicit invocation;
- configure the release trust policy;
- initialize real personal state;
- run target models, holdouts, human labels, or a pilot;
- create authority keys or signatures;
- claim ICF or NIST certification;
- claim coaching efficacy or human equivalence.

## Acceptance path

Codex should first reproduce repository qualification on the exact branch. It
should then decide whether to integrate each candidate asset into the canonical
suite and ledgers. Host implementation, target-model execution, independent
holdouts, English/Chinese human review, named-host privacy verification, and a
consented pilot remain separate evidence gates.
