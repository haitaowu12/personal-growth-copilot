# Qualification operations

## What the repository can complete

The repository implements the schemas, builders, run orchestration, source-pack
assembly, witness payloads, replay verification, readiness reporting, and
promotion application for all nine canonical release gates:

1. behavioral qualification;
2. reviewer attestation;
3. immutable attempt inventory;
4. independent untouched holdout;
5. named-host privacy preflight;
6. bilingual review;
7. controlled pilot;
8. independent release review; and
9. owner promotion.

It cannot create a person's identity or independence, observe a host control,
invent a participant outcome, author its own untouched holdout, or sign on behalf
of an independent authority. Those are the remaining irreducible inputs.

## Initialize the packet

```bash
python scripts/qualification_packet.py init \
  --packet-root /private/pgc-qualification

python scripts/qualification_packet.py intake \
  --packet-root /private/pgc-qualification \
  --output /private/pgc-qualification/external-intake.json

python scripts/qualification_packet.py work-plan \
  --packet-root /private/pgc-qualification \
  --output /private/pgc-qualification/external-work-plan.json
```

The work plan is candidate-bound and lists the exact prerequisites, commands,
schemas, builders, output folders, completion conditions, and external
observations for every gate. It contains no signature, identity, case, host
observation, participant record, or passage claim.

## External source construction

`scripts/external_source_builder.py` provides create-only operators for:

- exact reviewer use, identity, independence, calibration, and bilingual source
  reconciliation;
- holdout seal, author evidence, access audit, case result, externally witnessed
  attempt ledger, and source assembly;
- privacy host identity, seven-control audit, findings, witness request, and
  signed source assembly; and
- pilot preregistration, exact episode schedule, consent/withdrawal/deletion
  evidence, incidents, witness request, and signed source assembly.

The builder calculates file hashes, object self-hashes, event chains, coverage,
and witness payloads. Private keys are never accepted. `assemble-*` commands
verify externally returned signatures before creating a source pack.
Exact declaration-file fields and examples are in
`EXTERNAL_SOURCE_INPUTS.md`.

## Outcome evidence

`scripts/outcome_evaluation.py` requires an explicit record for every
episode/system/measure/collection-point combination. Each entry is `OBSERVED`,
`MISSING`, `DECLINED`, or `NOT_DUE`; observed entries require source evidence and
hashes. Fixed primary outcome rules cannot be replaced after results are seen.

`scripts/learning_feasibility.py` separately requires independent topic and
answer-key review, baseline and content-matched comparison tasks, immediate and
seven-day transfer, two distinct condition-blinded artifact reviewers, burden,
help use, missingness, and withdrawals.

Both analyses report distributions and retain adverse or absent observations.
Neither authorizes an efficacy claim.

## Readiness and promotion

```bash
python scripts/release_readiness.py \
  --output /private/evidence/release-readiness.json
```

The expected pre-observation status is
`REPO_COMPLETE_EXTERNAL_PENDING`: repository machinery is complete while one or
more external gate observations remain absent. `REPO_GAPS` means code or a
required schema/operator is missing. `PRODUCTION_PROMOTED` requires the current
verified evidence index to be promoted.

After all nine current receipts pass and the owner has signed promotion:

```bash
python scripts/apply_verified_release.py \
  --index /private/pgc-qualification/evidence-index.json \
  --policy /private/pgc-qualification/trust-policy.json \
  --expected-policy-sha256 <owner-policy-hash> \
  --expected-index-sha256 <owner-current-index-hash> \
  --output /private/pgc-qualification/promotion/release-manifest.json
```

The command refuses an eligible-but-not-promoted index, a partial gate set,
candidate drift, a stale current-index anchor, a dirty checkout, or any failed
signature. It never edits historical evidence or silently flips the committed
research candidate to production.

## Stop conditions

- Do not substitute auxiliary model review for human review.
- Do not omit failed attempts, withdrawals, non-attempts, missing reviews, or
  incidents.
- Do not grant persistence from adapter availability or local drill passage.
- Do not reveal holdout content to candidate authors after freeze.
- Do not accept a signature created by the run operator for an independent role.
- Do not publish a production, superiority, learning-effectiveness, or efficacy
  claim before its exact current evidence gate passes.
