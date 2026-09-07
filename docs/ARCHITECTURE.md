# Architecture

## Runtime layers

```text
Explicit user invocation
        |
        v
SKILL.md orchestration contract
        |
        +--> safety observation -> deterministic safety state
        |                            +--> memory write gate
        |                            +--> host current-resource resolver
        |
        +--> context_runtime -> consent/materiality/one-question/saturation
        |                         +--> user-defined scales and decisions
        +--> collaborative inquiry + visible context model (deep sessions)
        +--> one task-specific knowledge reference
        +--> safety/scope reference when material
        |
        v
Visible working model -> chosen experiment -> review
        |
        +--> optional exact-delta memory proposal
                 |
                 v
          host-confirmed persistence only
```

## Responsibility split

### Model responsibility

- natural-language reflection;
- context-sensitive material questions;
- tentative hypotheses and alternatives;
- recommendation synthesis;
- rehearsal and review conversation.

### Deterministic responsibility

- skill and release validation;
- behavioral-case contract validation;
- canonical Draft 2020-12 record validation with format enforcement;
- prohibited-field, correction-target, and referential-integrity checks;
- no-overwrite record initialization;
- host-neutral preview, single-delta consent, atomic commit, revision,
  correction, revocation, export, and deletion conformance;
- CI and provenance checks.
- named safety-state transitions, sticky post-crisis memory freeze, transition
  guards, and content-free audit events;
- current-resource freshness validation, resolver failure normalization, and
  exact rendered-contact matching;
- host-classified exact-question consent, material-question gating, saturation,
  user-approved scale definitions, host-attested score entry, temporal status,
  and user-owned decisions;
- branch execution, variants, repetitions, baseline slots, transcript/result
  hashing, and hard-gate aggregation in the evaluation harness.
- byte-snapshotted stdio-provider identity, reserved-environment denial,
  preregistered run matrix, resumable target capture, opaque review-packet
  import, quality thresholds, and deterministic target replay.
- cumulative system-blinded review-request export, calibrated-reviewer
  attestation references, exact full-suite submitted-result reconciliation,
  paired non-inferiority aggregation, and explicit conditional/evidence-blocked
  status until external reviewer and attempt-inventory receipts exist.

### Host responsibility

- model selection and inference;
- current crisis-resource lookup when needed;
- privacy, transport, and retention disclosures;
- permissioned file or memory operations;
- proof of write, correction, export, and deletion;
- installation and activation state.

The host, not the model, is the trust boundary for resource currency, user
location input, model invocation, persistence, and human-review identity. A
model-authored safety state, consent assertion, resource contact, or persistence
result is untrusted until the corresponding deterministic or host control
confirms it.

## Safety control flow

```text
user meaning -> model/host risk observation (not keyword-only)
                    |
                    v
            safety_runtime transition
              |         |          |
              |         |          +--> opaque state audit
              |         +--> memory write allowed/blocked
              +--> ACUTE_DANGER? --> minimal jurisdiction --> host resolver
                                                |               |
                                                |               +--> current verified contacts
                                                +--> missing/failure -> generic immediate route
```

The runtime contains no crisis directory and receives no conversation text.
Post-crisis return does not thaw the memory latch; a later explicit re-enable
event is required.

## Knowledge routing

The 260-line lead skill stays below the 500-line budget. It loads two core
references for deep inquiry and only one or two task references. Evidence and
community research remain outside the runtime package except for a compact
runtime evidence ledger.

## Continuity model

The portable JSON record is deliberately not a database implementation.
`scripts/record_store.py` supplies a thread-safe, non-persistent in-memory
conformance target for exact previews, verified host attestations, store-owned
time, opaque revisions, atomic validation, correction, export, and verified
content deletion across revisions and pending previews. An eventual persistent
adapter must preserve those semantics and pass host privacy preflight before
real state.

Schema `1.1` stores evidence as typed, referenced items rather than free-text
hypothesis support; stores scale definitions separately from user-entered
check-ins; preserves the model recommendation separately from the user's
selected option; and requires explicit review points instead of assuming a
permanent profile. Review-due material must be reconfirmed before use.

## Evaluation layers

1. structural repository and skill validation;
2. deterministic growth-record tests;
3. executable safety controls and branchable harness conformance;
4. authored target/baseline transcript execution and calibrated review;
5. calibrated human review and bilingual adjudication;
6. untouched holdouts;
7. consented privacy-safe pilot;
8. independent release review and owner decision.

External gate claims cross a cryptographic trust boundary defined in
`docs/RELEASE_EVIDENCE.md`. Role-scoped Ed25519 receipts bind every gate artifact
to the exact candidate; every role requires a distinct trusted key, and the
configured policy must match an owner-distributed out-of-band hash. The default
trust policy is unconfigured, so local code cannot self-promote.

The current alpha completes layers 1–3 on synthetic controls and implements a
development-only transport/review/campaign protocol needed by layer 4. The stdio
adapter is a trusted executable with the ambient filesystem and network rights
of its host process; the runtime does not provide an OS sandbox or verify the
remote model identity. Imported reviewer identities remain externally
unverified; hash-shaped attestation references are not accepted as proof.
The Codex adapter rejects recorded tool activity after a turn, which is not a
confidentiality sandbox. The harness run is deliberately labeled conformance evidence and
cannot prove model behavior. It has not executed or passed layers 4–8.

## Optional source-grounded learning lane

Explicit topic-learning requests can use the portable offline player. Python validates
source identity, schema, prerequisites, and question keys; one JavaScript reducer owns
progression, evidence labels, review timing, and imported-history replay. The same
reducer runs under Node during development checks. The player renders plain text under
a restrictive CSP, makes no network requests, and saves only after a user selects
browser saving or export. This educational store does not qualify the coaching store
or sensitive-state persistence. See `LEARNING_RELEASE.md` for the acceptance boundary.
