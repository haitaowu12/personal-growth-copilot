# Personal Growth Copilot

Standalone clean-room development repository for an explicit-invocation Agent
Skill supporting context-rich personal growth, reflective dialogue, practical
behavior-change experiments, and longitudinal learning.

Current version: `0.4.0-alpha.9`

This repository does not contain or claim byte equivalence to the unavailable
historical `0.2.0-rc.1` candidate. See
`provenance/HISTORICAL_LINEAGE.md`.

## Product boundary

`personal-growth-copilot` owns the user's internal change system: values,
goals, recurring patterns, experiments, reflection, practice, and retained
learning. `interpersonal-strategist` separately owns concrete relationship and
interaction decisions. Overlap is allowed; activation remains explicit.

## What this alpha adds

- a consent-based, one-question-at-a-time inquiry loop;
- a visible and correctable context model rather than hidden profiling;
- optional user-owned growth records with typed evidence, transparent scales,
  user-entered check-ins, temporal review points, and decision history;
- canonical-schema validation and a non-persistent consented record-store
  conformance target;
- evidence-linked methods for motivation, goal design, small experiments, and
  review;
- community-pattern provenance without copying donor implementations;
- a 13-case, 58-turn authored development suite with alternate branches,
  paraphrases, repetitions, both matched baseline slots, per-turn events, and
  state assertions;
- an executable five-state safety control, sticky crisis memory freeze, and a
  current-resource resolver interface that fails without fabricating contacts;
- a deterministic 309-run harness-conformance artifact with complete synthetic
  transcripts and result hashes;
- an executable context control for host-attested inquiry consent and
  materiality, one-question flow, saturation, exact user-approved scale and
  score actions, and user-owned choice;
- a development-only, secret-free provider protocol with byte-snapshotted
  execution, a frozen suite/baseline/run matrix, resumable capture, opaque
  externally-unverified reviewer packets, quality floors, hard-failure
  preservation, and deterministic target-run replay;
- a cumulative blinded review-request artifact covering all eleven governed
  rubric dimensions, exact transcript/structured observations, event candidates
  without gold polarity, and an exact review-request hash;
- a full-suite result manifest and deterministic campaign aggregator that
  rejects missing, duplicate, extra, tampered, symlinked, or response-ID-reused
  submitted results and binds the suite to canonical repository bytes. It
  cannot prove that no alternate attempts were omitted,
  so it reports only a conditional submitted-matrix result and keeps campaign
  completion and reviewer evidence blocked;
- an unconfigured release-only attempt wrapper that records provider starts,
  completions, failures, final results, and campaign sealing in a stateful
  external Ed25519 witness chain, then reconciles every signed event against
  the exact verified result files and an out-of-band current head/count;
- a development-only Codex CLI adapter with complete target/baseline profile
  hashes and event-stream rejection of tool activity; it still requires a
  dedicated restricted host and credentials;
- a create-only canonical release-packet builder and role-scoped Ed25519 receipt
  verifier for behavioral, reviewer, attempt,
  holdout, privacy, bilingual, pilot, independent-review, and owner-promotion
  evidence, bound to owner-distributed out-of-band policy and current-index
  hashes. Its committed trust policy is deliberately unconfigured and cannot
  promote the release.
- source-replayed reviewer, holdout, privacy, bilingual, and pilot gate packs,
  with preregistered witness keys for attempt, host-audit, and pilot-ledger
  completeness
  that bind retained evidence files, derive thresholds and completeness from
  structured records, reconcile reviewers and bilingual scores against the
  exact target results, and reject a signed PASS made only from booleans and
  arbitrary hashes.
- a create-only private qualification-packet initializer and fail-closed
  preregistration preflight. It creates no identities, evidence, private keys,
  holdout cases, or pilot records; it reports each real input as `MISSING`,
  `INVALID`, or `VALID`, validates available inputs immediately, and reuses the
  trust-policy validator before a candidate can be frozen.
- a read-only named-host privacy discovery that records bounded storage,
  encryption, declared-sync, and backup observations without retaining raw
  command output. It cannot generate a privacy PASS, authorize persistence, or
  convert unexecuted lifecycle and incident controls from `UNKNOWN`.

The copilot may feel conversationally similar to a thoughtful coach. It must
not claim to be a therapist, simulate a clinical relationship, diagnose, mine
trauma, or encourage emotional dependence.

## Status

Standalone research alpha. Not installed, registered, implicitly invoked,
production-qualified, or approved for real sensitive-state initialization.

Run local checks with:

```bash
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements/ci.txt
.venv/bin/python scripts/run_deterministic_qualification.py
```

The qualification command refuses to emit passing evidence from a dirty tree.
Its artifact is deterministic-controls evidence only, not behavioral, privacy,
pilot, efficacy, or release evidence.

The evidence ladder is intentionally non-cumulative: repository integrity,
deterministic controls, authored target/baseline evaluation, independent
holdouts, named-host privacy/security preflight, controlled pilot, independent
release review, and owner promotion each require their own exact evidence.
Synthetic expected-event fixtures prove only that the harness works.
The target adapter, review, and campaign tests prove only that the evidence path
fails closed; no real target-model run or human qualification is claimed yet.
See `docs/RELEASE_EVIDENCE.md` for the signed external-evidence contract.
