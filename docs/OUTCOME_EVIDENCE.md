# Product and learning outcome evidence

## Product outcomes

The governed design in `evals/outcome-measures.json` separates process, proximal,
delayed, burden, and dependence measures. Two primary outcomes are fixed before
execution:

- user-confirmed clearer choice or better-specified uncertainty; and
- completion of an evidence-linked learning loop at the agreed review point.

`evals/outcome-observations.schema.json` requires exact coverage for every
episode, system, measure, and collection point. Observations cannot disappear:
they must be classified as observed, missing, declined, or not due. Withdrawn and
dropout episodes remain on the roster. Observed entries bind an evidence file,
timestamp, and SHA-256.

Run:

```bash
python scripts/outcome_evaluation.py validate \
  --observations /private/evidence/pilot/outcomes.json

python scripts/outcome_evaluation.py analyze \
  --observations /private/evidence/pilot/outcomes.json \
  --output /private/evidence/pilot/outcome-result.json
```

Primary rates retain missing, declined, and adverse observations in the
denominator. `NOT_DUE` is excluded only because the governed collection point has
not occurred. Process scores, duration, disclosure, or return frequency cannot
replace primary outcomes.

## Learning feasibility

Before participant evidence, an independent reviewer must attest source accuracy,
answer keys, and rubric alignment against the exact topic hash. Each participant
then retains five task slots:

- fresh baseline;
- player immediate transfer;
- player seven-day transfer;
- source-reading immediate transfer; and
- source-reading seven-day transfer.

Observed artifacts require two distinct condition-blinded reviewers scoring the
four fixed 0–2 criteria. Missing and withdrawn tasks retain empty evidence slots
rather than disappearing. Analysis reports score distributions, reviewer
difference, time, help use, withdrawal, and missingness by condition and
timepoint.

```bash
python scripts/learning_feasibility.py \
  --observations /private/evidence/learning/observations.json \
  --output /private/evidence/learning/feasibility-result.json
```

This is a feasibility analysis. It is not a powered causal study, certification,
mastery claim, or substitute for the coaching product's nine release gates.

