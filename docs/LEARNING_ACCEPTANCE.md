# Learning candidate acceptance

Candidate: `0.5.0-alpha.1`; topic: `requirements-writing@1.0.2`; rubric/protocol: `1.2`.
This is a development candidate for human review, not a production or efficacy claim.
See `LEARNING_REHEARSAL.md` for the model-only review and repair record.

## Current operational evidence

On 2026-10-03, the Codex in-app browser ran synthetic exercises on loopback-served
portable HTML. Topic 1.0.1 completed all three concepts, saved/resumed and exported
an actual progress file. Topic 1.0.2 completed the direct diagnostic/application/
writing/self-review route for all three concepts, used a measurement hint, recorded
worked-writing-example exposure, exported a real JSON file, and resumed 3/3 after
reload. Zero checked writing criteria remained visibly uncertain rather than being
promoted to a passing grade. These are operational checks, not learner observations.

The revised in-page confirmations were exercised for unsaved navigation, imported
progress replacement, and clear. Cancel/Escape preserved the draft and restored
focus. Valid import required confirmation, kept saving off, and preserved the old
browser copy. Malformed JSON, wrong-topic-version, future-timestamp and oversized
imports were rejected without replacing current work. Clearing 1.0.2 and reloading
showed 0/3 while the older 1.0.1 browser copy still resumed 3/3.

A sandboxed iframe denied localStorage for the current lesson. Load/save failure
kept persistence off and reported export as the recovery path. Clear reported that
only tab progress could be cleared and that browser data, downloads and backups
might remain. The full-journey page had no captured warning/error console entries.
These observations and HTML hashes are retained in the local rehearsal receipts.

The earlier native-confirmation stall is historical. In-page navigation/import/clear
dialogs now work in this host; the native tab-close `beforeunload` path is a separate
remaining check. The initial full 1.0.2 journey predates follow-up changes. The final player was then
checked in two tabs: a new saved answer disabled saving in the stale tab; clearing
that stale tab retained the newer browser copy, which resumed correctly. Actual
unsaved-draft and recorded-history downloads preserved the dirty draft. Those
checks used the same final player code with the immediately preceding topic hash.

Final topic SHA-256:
`6f43f8a93ade1d4688d98bc63e7fc5d58c00128c43702b564657ba64e116112e`.
On that exact topic, a wrong diagnostic led through explanation, practice, transfer,
writing, worked-response exposure and self-review; export/reload resumed 1/3 with
saving enabled. Full-page visual inspection at an actual width of 375 pixels showed
readable writing/completion content and a 337-pixel dialog within the viewport;
Escape canceled it. All three concepts were not rerun after the last wording edits.
The local `browser-final-receipt.json` distinguishes these scopes and HTML hashes.

## Deterministic checks

Production-player tests cover persistent save warnings, changed-copy preservation,
2000-event draft rescue and asynchronous import confirmation/cancellation.
Topic validation, strict event replay, content/version binding, first-attempt and
help accounting, delayed-review policy, progress limits, package allowlisting,
per-file checksums and rebuilding solely from the extracted skill are automated.
The existing coaching, safety, record, provider and release suites remain required.
Neither their success nor a package hash proves teaching quality or learner benefit.

```bash
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements/ci.txt
# Node.js 22 is a development prerequisite.
.venv/bin/python scripts/run_deterministic_qualification.py
.venv/bin/python scripts/package_learning.py --out build/learning-candidate.zip
```

Qualification binds to a clean commit. Its JSON receipt is authoritative for exact
counts and source hashes. Review worksheets and model reports are not learner data.

## Remaining host and human gates

- Direct `file://` navigation was rejected by the in-app browser URL policy. No
  alternate surface or workaround was used. A permitted target host must test the
  packaged HTML directly, including portable exports when storage is unavailable.
- The first 390-pixel override did not resize its tab; a later test produced an
  actual 375-pixel viewport with no document overflow and an inspected dialog.
  Confirm the named pilot device dimensions rather than assuming the requested size.
- Use one active lesson tab for rehearsal. Snapshot checks and storage events reduce
  stale writes but are not atomic against simultaneous writers; multi-tab support
  needs serialization and actual-device acceptance before being claimed.
- Complete keyboard-only and assistive-technology journeys, zoom, long drafts,
  reduced motion, tab-close warning, offline operation and a network trace on the
  actual pilot devices. CSP and embedded assets support the intended offline design;
  source inspection is not a substitute for those device checks.
- Human source fidelity, answer-key review and all 21 exact-topic worksheet decisions
  remain pending. Confirm named owners, consent, privacy/retention, reserved forms,
  scorer calibration and the frozen device scope before learner recruitment.

The wider coaching product's behavioral comparison, untouched holdouts, bilingual
review, host privacy, pilot and owner promotion gates remain separate and blocked.
