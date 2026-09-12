# Learning candidate acceptance

Candidate: `0.5.0-alpha.1`; topic: `requirements-writing@1.0.0`.

## Implemented and checked

- Source-linked topic format with explicit prerequisites, cycle/reference/answer
  checks, and HTTPS-only source links.
- Distinct diagnostic, remediation, practice, transfer, writing, self-review,
  and delayed-review stages.
- Shared deterministic reducer with immutable first attempts, visible assistance,
  bounded written applications, strict event replay, content/version binding,
  byte limits, clock checks, and no imported derived score or mastery claim.
- Portable HTML compiler with escaped data, a restrictive CSP, no remote fonts or
  imagery, and a reproducible ZIP assembled from an explicit allowlist.
- Package rebuild parity from only the distributed skill folder outside the
  repository.
- Packaged-file browser acceptance using Playwright Core and an installed
  Chromium browser. The runner blocks HTTP and HTTPS requests, records console
  and page errors, and emits a JSON evidence receipt.

The local run on September 11, 2026 (America/Vancouver) used Google Chrome
`152.0.7977.83` on macOS and passed these scenarios:

1. Keyboard entry into practice and keyboard answer submission with feedback
   focus; wrong diagnostic remediation; wrong then correct practice; transfer;
   all three written applications and self-reviews; one hinted path.
2. Opt-in browser saving, reload/resume, opt-out, scoped removal, and fresh reload.
3. Export, valid import, malformed JSON rejection, wrong-version rejection,
   future-timestamp rejection, unchanged current progress, and clear.
4. Simulated storage denial for both save and delete paths, with in-tab recovery
   and user-visible failure messages.
5. Direct `file://` execution from the extracted release ZIP at 390 pixels with
   reduced motion, no horizontal overflow, no console/page errors, and no network
   requests.

## Reproduce

```bash
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements/ci.txt
npm ci --ignore-scripts --no-audit --no-fund
.venv/bin/python scripts/run_deterministic_qualification.py
.venv/bin/python scripts/package_learning.py --out build/learning-candidate.zip
.venv/bin/python -c "import zipfile; zipfile.ZipFile('build/learning-candidate.zip').extractall('build/learning-package')"
npm run test:learning-browser -- \
  --html build/learning-package/requirements-writing.html \
  --evidence build/evidence/learning-browser-acceptance.json
```

Set `PGC_BROWSER_EXECUTABLE` when Chrome, Edge, or Chromium is installed outside
the runner's known paths. The GitHub workflow runs this browser check once on the
pinned Ubuntu image rather than repeating it across the Python matrix.

The deterministic qualification command binds its receipt to the current clean
commit. The browser receipt binds the exact HTML bytes and observed browser
version. Package and HTML hashes establish byte identity, not learning quality.

## Remaining evidence limits

This candidate has one local Chromium-engine result. It has no observed Safari,
Firefox, real-phone, screen-reader, switch-control, 200% browser-zoom, or manual
visual-regression evidence. Storage denial was induced by replacing the browser
storage methods before page load; that exercises the product path but does not
represent every operating-system or browser storage failure. CI browser evidence
becomes available only after the workflow runs on the committed candidate.

Independent source and answer-key review, usability with real learners, unseen
transfer, seven-day retention, and learning-effectiveness evidence remain open.
Coaching behavioral comparison, untouched holdouts, bilingual human review,
named-host privacy, controlled pilot, independent release review, and owner
promotion remain blocked. No production, broad browser-compatibility, mastery,
or learning-efficacy claim is authorized by this candidate.
