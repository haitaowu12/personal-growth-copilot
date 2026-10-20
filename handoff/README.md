# Historical evidence-rebalancing handoff

The following three files are preserved byte-for-byte from PR #10 head
`26f244dbbd3dea73edd0d5139adac9b9cd8b1b93`:

- `CODEX_FINAL_CHECK_20260813.md`
- `CODEX_FINAL_CHECK_FILES.sha256`
- `CODEX_FINAL_CHECK_MANIFEST.json`

They describe the August 2026 branch based on
`767fa96ca51116f916997d04a8cf3cff67ee9515`, its implementation at
`0774e9568673c89061f0cddf9ffb74d27574ac82`, and subsequent historical checks.
They retain old skill paths, baseline locations, capsule fields, and test
counts for provenance. Their instructions and results do not apply to the
current integrated tree. In particular, historical CI results are not evidence
for this integration or for target behavior, host qualification, or release.

The current integration dispositions are in `docs/EVIDENCE_REBALANCING.md`.
The canonical skill lives under
`plugins/personal-growth-copilot/skills/personal-growth-copilot/`; capsule
persistence uses `status` and `host_receipt_sha256`, and comparator designs live
under `evals/comparators/`. Follow the current repository contracts and run
`scripts/run_deterministic_qualification.py` on the exact clean candidate for
current deterministic evidence. That runner does not call GitHub Actions or
execute the research cases against target models.

From this directory, `sha256sum --check CODEX_FINAL_CHECK_FILES.sha256` verifies
the two historical artifacts listed by the original checksum file. The
checksum file itself is also preserved from the original PR head.
