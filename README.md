# Personal Growth Copilot

Standalone clean-room development repository for an explicit-invocation Agent
Skill supporting context-rich personal growth, reflective dialogue, practical
behavior-change experiments, and longitudinal learning.

Current version: `0.3.0-alpha.3`

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
- optional user-owned growth records and transparent check-in scales;
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
  transcripts and result hashes.

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
