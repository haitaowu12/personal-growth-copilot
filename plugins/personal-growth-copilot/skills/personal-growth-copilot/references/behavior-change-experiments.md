# Behavior-change experiments

## Diagnose the barrier before choosing a technique

Use a plain-language barrier map:

- **clarity:** the desired behavior or decision is vague;
- **capability:** knowledge, skill, energy, or health-relevant limitation;
- **opportunity:** time, access, environment, incentive, or support;
- **motivation:** value conflict, ambivalence, confidence, or delayed payoff;
- **initiation:** intention exists but the start cue is weak;
- **persistence:** friction or interruption breaks the action;
- **feedback:** results arrive late or are hard to see;
- **recovery:** one miss becomes abandonment or self-attack.

The map is a hypothesis. Ask the user to correct it.

## Select an active ingredient

| Barrier | Candidate technique | Fit check |
|---|---|---|
| Clarity | define behavior, outcome, or decision | Is ambiguity actually the blocker? |
| Capability | instruction, modeling, rehearsal, graded practice | Can the skill be practiced safely here? |
| Opportunity | remove friction, add resource, restructure environment | Is the environment change authorized and reversible? |
| Motivation | values link, pros/cons, desired-future/obstacle contrast | Does the user want exploration rather than persuasion? |
| Initiation | if-then plan, prompt, calendar cue | Is the underlying intention already strong? |
| Persistence | minimum version, coping plan, social support | What predictable interruption must the plan survive? |
| Feedback | self-monitoring, outcome signal, review event | Will tracking inform action rather than create burden? |
| Recovery | reset rule, self-compassionate debrief | What is the smallest restart after a miss? |

Technique names describe active content. They do not prove effectiveness for a
particular person.

## Candidate technique registry

`assets/technique-registry.json` is a candidate research and evaluation aid,
not a requirement for active experiment records or a validated prescription.
Its eligibility and contraindication rules are hypotheses to evaluate; they do
not establish user fit or safety. Use ordinary language with the user and
preserve these features of an experiment:

- the barrier hypothesis and a plausible alternative;
- the chosen active ingredient and the user's reason for trying it;
- the expected proximal signal and what would disconfirm it;
- minimum burden, a feasible review window, and the user's choice to proceed or decline.

Keep research identifiers separate from record fields. `PGC-BCT-*` and `BCIO:*`
name registry entries and ontology concepts; they are neither record-local
evidence IDs nor external `source_citation_id` values. The ontology's
`evidence_source_id` can reference candidate research such as
`bcto-2023-ontology`; that naming provenance is not admitted runtime evidence.

For a growth record, use only fields supported by
`assets/growth-record.schema.json`. An optional external citation belongs in an
evidence item with `origin_kind: EXTERNAL_SOURCE`, and its
`source_citation_id` must occur in `assets/evidence-source-ids.json`. The
registry's per-technique `evidence_source_ids` are limited to that canonical
allowlist, but include a citation only if it supports the specific recorded
statement. If none applies, omit the optional external citation rather than
substitute a candidate or taxonomy ID. Hypothesis `supporting_evidence_ids`
refer to IDs of evidence items in this record, not directly to research
citations. Keep candidate mapping traceability in research/evaluation artifacts.

Ontology membership and a citation do not establish product efficacy or fit
for this user. When an attempted technique fails to produce its predicted
signal, revisit the hypothesis, fit, or technique rather than explain away
the result. A blocked or unattempted action leaves the prediction untested;
record the barrier instead of claiming success or disconfirmation.

## Experiment card

```text
Question
What are we trying to learn or change?

Hypothesis
If ..., then ..., because ...

Technique
Chosen active ingredient in ordinary language.

Action
Exact behavior, time/place, duration, and minimum version.

Trigger and coping plan
If [cue/obstacle], then I will [response].

Evidence
What observable signal will count? What would disconfirm the hypothesis?

Window
Start, end, and review event/date.

Risk and stop condition
What could go wrong? When should the user pause or seek help?

Support
Which person, tool, skill, or environmental change is needed?

Learning value
What will be useful even if the outcome is negative?
```

## Small means informative, not trivial

Prefer an experiment that is:

- within the user's authority;
- low-regret and reversible;
- observable within a short window;
- feasible in a difficult but realistic week;
- capable of distinguishing at least two explanations;
- connected to the user's stated goal.

Do not shrink an action until it loses meaning. Do not use a tiny step to avoid
a necessary real decision.

## Proximal and delayed observations

Separate an immediate process signal, such as a clearer choice, from a later
observation at the agreed review event. Agreement, encouragement, or one
favourable result does not establish that the technique caused improvement.
Keep the original prediction visible before reviewing the result.

Record non-attempts, blocked opportunities, burden, missing reviews, withdrawal,
and dropout alongside attempts. Do not retrospectively change the success
criterion or select only favourable episodes. A useful review can narrow or
retire a hypothesis, support intentional non-action, or reduce unnecessary
tracking without demonstrating a general treatment effect.

## Mental contrasting plus if-then planning

Offer, do not impose:

1. desired outcome;
2. most relevant internal or external obstacle;
3. one controllable response;
4. if-then plan linking the obstacle or opportunity to that response.

Do not use imagery to intensify distress. Do not treat every obstacle as an
internal mindset problem.

## Recovery rule

A miss is an observation. Review whether the action was unclear, too large,
poorly cued, unsupported, blocked by context, not actually valued, or made
unsafe by new information. Change one design variable at a time when practical.
