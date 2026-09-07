# Learning candidate acceptance

Candidate: `0.5.0-alpha.1`; topic: `requirements-writing@1.0.0`.

## Implemented and checked locally

- Source-linked topic format, explicit prerequisites, cycle/reference/answer checks.
- Distinct diagnostic, practice, transfer, and delayed-review scenarios.
- Shared deterministic reducer, remediation, first-attempt history, assistance labels,
  written application, explicit self-review, and scheduled retrieval.
- Strict event replay, content/version binding, byte limits, clock checks, and no
  imported derived score or independent-mastery assertion.
- Portable HTML compiler with escaped data and CSP; JavaScript syntax checks.
- Reproducible ZIP from an explicit source allowlist, per-file checksums, and rebuild
  parity from only the packaged skill outside the repository.
- Existing coaching, safety, record, provider, and release tests retained.

Reproduce:

```bash
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements/ci.txt
# Node.js 22 is a development prerequisite.
.venv/bin/python scripts/run_deterministic_qualification.py
.venv/bin/python scripts/package_learning.py --out build/learning-candidate.zip
```

The qualification command binds results to the current clean commit. Its JSON receipt
is the authority for exact counts and hashes. A package checksum proves byte identity,
not learning quality.

## Required acceptance still open

Browser inspection was requested during development but host browser security policy
reported that the user declined localhost access. No alternate browser path was used.
Desktop/mobile screenshots, keyboard/focus checks, actual storage failures,
export/import/clear UI behavior, and end-to-end browser evidence remain **unverified**.
Browser support is an implementation target, not an observed compatibility claim.

Required next browser scenarios:

1. Fresh session with saving off; keyboard-only start and diagnostic answer.
2. Wrong diagnostic -> example -> wrong/correct practice -> transfer -> writing ->
   self-review -> next concept; verify actual feedback and first-attempt counts.
3. Correct diagnostic skips remediation; use a hint and verify assistance remains
   visible; complete all three written applications.
4. Enable saving, reload, resume; disable saving and verify scoped removal.
5. Export/import a real progress file; reject wrong-version, malformed, oversized,
   future-timestamp, and inconsistent-result files without losing current work.
6. Clear this topic; verify wording and behavior when browser storage is denied.
7. Exercise 390-pixel and desktop layouts, long drafts, zoom, focus, reduced motion,
   offline operation, console health, and zero unexpected requests.
8. Open the packaged HTML directly, not just from a development server. Confirm
   portable exports where file-origin storage is unavailable.

Independent source/answer-key review and actual learner transfer/retention evidence
also remain open. See `LEARNING_PILOT.md`. Coaching behavioral comparison, untouched
holdouts, bilingual review, host privacy, pilot, and owner promotion stay blocked.
No production or learning-efficacy claim is authorized by this candidate.
