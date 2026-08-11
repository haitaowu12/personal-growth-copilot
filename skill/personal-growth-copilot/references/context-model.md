# Context model

## Principle

Tailoring requires a dossier-like working model, but it must be transparent,
purpose-limited, correctable, and user-owned. A useful model helps decide what
to ask, recommend, test, or remember. It is not a personality verdict.

## Model layers

### Current episode

- situation and sequence;
- people or systems involved, minimized and de-identified where possible;
- user-reported thoughts, emotions, bodily state, urges, and actions;
- immediate stakes, deadline, and constraints.

### Direction

- desired outcome and time horizon;
- values or needs the user names;
- boundaries and non-negotiables;
- approach and avoidance motives;
- what “good enough” would look like.

### Change system

- capability: knowledge, skill, energy, health-relevant limits as reported;
- opportunity: time, access, environment, incentives, social support;
- motivation: importance, confidence, ambivalence, expected payoff;
- prior attempts, exceptions, partial successes, and recovery patterns.

### Working hypotheses

For each hypothesis record:

- statement;
- supporting evidence;
- disconfirming or missing evidence;
- context boundary;
- confidence: low, medium, or high;
- alternative explanations;
- test or observation that would update it.

### Continuity

- active experiment and review event/date;
- observed outcome and learning;
- durable preference, explicitly confirmed;
- corrections and superseded hypotheses;
- memory consent and scope.

## Provenance labels

- `USER-REPORTED`: directly stated by the user.
- `OBSERVED-IN-CHAT`: visible in supplied text or action, without hidden-state
  inference.
- `HYPOTHESIS`: an interpretation offered for correction.
- `ALTERNATIVE`: a competing explanation.
- `UNKNOWN`: information that could matter but is absent.
- `CORRECTION`: the user's revision of a prior record or interpretation.

When stakes are high, attach a label and date/context to each material claim.
In a retained record, give the claim an evidence ID and link hypotheses and
decisions to that ID. Do not keep free-text support that cannot be corrected or
superseded independently.

## Scores

Scores are permitted when transparent and useful. They are not banned; hidden,
diagnostic, and decontextualized scores are.

Use a scale only when it helps choose or compare. For every scale:

1. name the construct in ordinary language;
2. define both anchors for this context;
3. show the exact construct, range, anchors, purpose, decision link, context,
   and review point and let the user confirm or change them;
4. let the user provide the number;
5. record the date/event and why it matters;
6. compare primarily within the same user and context;
7. ask what makes the number that value and what would move it one step.

Examples: importance of this goal, confidence in this specific action, current
energy for this task, perceived progress since the last review.

Do not score personality, mental health, attachment, abuse, capacity, honesty,
risk, or another person's traits. Do not invent precision or population norms.
Do not import copyrighted or clinical instruments without authorization and a
qualified use path.

Store the scale definition separately from each check-in. Fix its construct,
bounds, anchors, purpose, decision link, context boundary, and review point.
Set `user_supplied: true` only from an actual user value. Pause an active scale
when metric fixation appears; never change anchors to improve a trend.

## Temporal validity and decisions

Do not assign a universal lifespan to personal information. Require an explicit
review point chosen for the item's purpose. At `review_at`, classify the item as
`REVIEW_DUE` and reconfirm, narrow, supersede, or remove it before material use.
Future-dated evidence is invalid; superseded, rejected, or retired material is
inactive.

For consequential choices, preserve viable options, benefits, costs,
reversibility, linked evidence, assumptions, unknowns, any model
recommendation, and the user's selected option. The recommendation never
becomes the recorded choice without the user's action.

Use `scripts/context_runtime.py` for consent, question materiality, inquiry
saturation, scale construction/check-ins, and choice ownership. Treat its
question classification, model-delta, scale, score, and choice attestations as
host trust boundaries; callers may not synthesize them from model text. Use
`scripts/growth_record.py` for schema, reference, temporal-order, and stale-item
validation.

## Materiality test

Before asking or storing, answer:

- Which recommendation, hypothesis, safety route, or experiment could this
  change?
- Could a less sensitive question answer it?
- Does the user understand why it matters?
- Is this for the current task or merely interesting?

If no consequential answer exists, do not ask or store it.

## Model presentation

Use a compact structure when showing the model:

```text
Known
- ...

Working interpretation
- ... (confidence; evidence)

Alternative
- ...

Tension
- ...

Unknown that matters
- ...

Correction invited
- What did I get wrong or overstate?
```

Do not present the full model every turn. Surface only the parts needed to
verify a consequential judgment.
