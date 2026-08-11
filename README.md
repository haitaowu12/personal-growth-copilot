# Personal Growth Copilot

Standalone clean-room development repository for an explicit-invocation Agent
Skill supporting context-rich personal growth, reflective dialogue, practical
behavior-change experiments, and longitudinal learning.

Current version: `0.3.0-alpha.1`

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
- evidence-linked methods for motivation, goal design, small experiments, and
  review;
- community-pattern provenance without copying donor implementations;
- structural behavioral cases covering inquiry quality, agency, safety,
  continuity, and anti-dependence behavior.

The copilot may feel conversationally similar to a thoughtful coach. It must
not claim to be a therapist, simulate a clinical relationship, diagnose, mine
trauma, or encourage emotional dependence.

## Status

Standalone research alpha. Not installed, registered, implicitly invoked,
production-qualified, or approved for real sensitive-state initialization.

Run local checks with:

```bash
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
python3 scripts/evaluate_contract.py
```
