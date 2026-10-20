# Outcome Evaluation Contract

Status: design-only and unexecuted. This contract does not qualify target
behavior, user benefit, pilot readiness, or efficacy.

## Measurement layers

Keep five layers separate:

1. **Process** — correction handling, evidence traceability, stopping, agency,
   and safety.
2. **Proximal outcome** — user-confirmed clearer choice or better-specified
   uncertainty after the session.
3. **Delayed outcome** — attempted action or intentional non-action,
   observation, and working-model update at the agreed review point.
4. **Burden** — disclosure, time, and turn cost.
5. **Dependence** — reliance, human-support displacement, and exposure.

`evals/outcome-measures.json` fixes two primary outcome IDs before target
execution. Do not substitute a more favorable outcome after observing results.
Failures, missing reviews, non-attempts, and dropouts remain visible.

## Comparator plan

The current direct and structured-reflection systems remain ablations. They do
not establish a strong comparison because both remove differentiated target
capabilities.

Four design-only definitions are recorded in `evals/comparators/`:

- `strong_generalist`: same model, safety policy, and approved context access,
  without the Personal Growth Copilot method;
- `minimal_visible_model`: facts, hypotheses, alternatives, unknowns, and one
  user-owned action without the extended coaching loop;
- `mi_informed`: nonclinical reflective conversation using the user's own
  reasons and choices, without a PGC dossier or technique references;
- `session_capsule`: direct assistance plus an explicitly requested preview of
  the canonical capsule, without adaptive longitudinal modeling.

All four require the same model, safety policy, and approved context access.
Their common memory policy is `READ_ONLY_USER_APPROVED`; no arm can silently
retrieve or write memory. The capsule arm previews a delta and does not claim a
write. A future write-enabled comparison needs a frozen common host contract.

These definitions are not governed execution slots yet. Before use, extend and
freeze the suite, target config, provider profiles, run identities, result
schemas, aggregation, reviewer requests, and attempt inventory. Re-run all
mutation and omission tests. Until then, no comparator result is claimed.

The 14 cases in `evals/ordinary-growth-cases.json` are likewise authored
research outside governed execution. Their proposed case-level outcomes do
not replace the two frozen primary outcome IDs in `evals/outcome-measures.json`.
See `docs/EVIDENCE_REBALANCING.md` for the integration dispositions and source
review limits.

## Session capsule

`plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/session-capsule.schema.json` defines a
compact explicit-save artifact. The capsule preserves user wording, facts,
hypotheses, alternatives, unknowns, choice, prediction, disconfirmation,
review point, and exact proposed memory delta. `previewed` is not a write;
`confirmed_by_host` requires a host receipt hash.

## Interpretation limits

- Process quality cannot substitute for user outcomes.
- More turns, time, disclosure, or returns do not imply success.
- External coaching or conversational-agent studies do not validate this
  product.
- Pilot data of the planned size may support feasibility and safety learning,
  not generalized efficacy.
- A named operational host, calibrated reviewers, untouched holdouts, and
  delayed observations remain required.
