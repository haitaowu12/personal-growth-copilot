# Architecture

## Runtime layers

```text
Explicit user invocation
        |
        v
SKILL.md orchestration contract
        |
        +--> collaborative inquiry + context model (deep sessions)
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
- portable record structure;
- prohibited-field and referential-integrity checks;
- no-overwrite record initialization;
- CI and provenance checks.

### Host responsibility

- model selection and inference;
- current crisis-resource lookup when needed;
- privacy, transport, and retention disclosures;
- permissioned file or memory operations;
- proof of write, correction, export, and deletion;
- installation and activation state.

## Knowledge routing

The 199-line lead skill stays below the 500-line budget. It loads two core
references for deep inquiry and only one or two task references. Evidence and
community research remain outside the runtime package except for a compact
runtime evidence ledger.

## Continuity model

The portable JSON record is deliberately not a database implementation. It
defines a host-neutral, inspectable contract. An eventual SQLite adapter must
preserve the same provenance, confirmation, no-clobber, correction, export, and
deletion semantics and must pass host privacy preflight before real state.

## Evaluation layers

1. structural repository and skill validation;
2. deterministic growth-record tests;
3. authored behavioral cases and hard safety gates;
4. model transcript execution;
5. calibrated human review and bilingual adjudication;
6. untouched holdouts;
7. consented privacy-safe pilot;
8. independent release review and owner decision.

The current alpha completes layers 1–2 and authors the contract for layer 3.
It has not executed or passed layers 3–8.
