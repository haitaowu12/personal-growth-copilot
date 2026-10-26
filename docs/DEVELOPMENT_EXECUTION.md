# Real-model development execution

## Purpose

The repository provides two distinct real-model lanes. They share the frozen
provider, system profiles, case suite, and tool-free execution boundary, but
they have different evidentiary meaning.

1. **Model-assisted development** executes selected real target, ablation, or
   comparator runs and uses a system-blinded auxiliary model reviewer. It is for
   finding behavioral defects before human qualification. Its artifacts always
   set `qualification_claim_allowed=false`.
2. **Authored qualification** executes the exact frozen 610-run matrix, pauses
   after every completion for calibrated human review, and records every attempt
   through the external witness protocol. Only this lane can feed the behavioral
   release gate.

Model review never establishes reviewer identity, independence, bilingual
meaning preservation, behavioral passage, efficacy, or production readiness.

## Prerequisites

- Clean checkout at the target config's exact commit.
- Absolute, non-symlink paths for `PGC_EVAL_REPO_ROOT`, `PGC_CODEX_BIN`, and
  `PGC_CODEX_AUTH_ROOT`.
- A target config produced by `scripts/build_target_config.py`.
- Provider quota and network access supplied by the evaluation host.
- No private user data in authored evaluation prompts.

The adapters accept a bounded inference runtime up to 512 MiB. This accommodates
the current standalone Codex distribution while retaining a hard file-size cap,
no-follow reads, exact SHA-256 binding, and private runtime snapshots.

## Bounded development campaign

Create reviewer settings containing only an optional `reasoning_effort`, then
freeze a selected case/system matrix:

```bash
python scripts/build_development_config.py \
  --target-config /private/evidence/target-config.json \
  --reviewer-adapter providers/codex_cli_review_adapter.py \
  --reviewer-adapter-version 1 \
  --runtime-executable "$PGC_CODEX_BIN" \
  --reviewer-model <model> \
  --reviewer-model-version <declared-version> \
  --reviewer-settings-file /private/evidence/reviewer-settings.json \
  --case-id advice-loop-saturation \
  --system-id target \
  --output /private/evidence/development-config.json
```

Run and verify it:

```bash
python scripts/development_campaign_cli.py run \
  --target-config /private/evidence/target-config.json \
  --config /private/evidence/development-config.json \
  --target-adapter providers/codex_cli_adapter.py \
  --reviewer-adapter providers/codex_cli_review_adapter.py \
  --output /private/evidence/development-result.json

python scripts/development_campaign_cli.py verify \
  --result /private/evidence/development-result.json
```

The result preserves every provider request/completion hash, response ID,
transcript, branch, automated failure, auxiliary review request, selected event,
score, uncertainty, and review-provider identity. Review prompts omit system
identity and limit labels to the supplied event and hard-failure codebooks.

## Exact qualification workspace

Initialize the exact run plan without hand-maintained filenames:

```bash
python scripts/campaign_workspace.py init \
  --workspace-root /private/evidence/behavioral-workspace \
  --config /private/evidence/target-config.json \
  --output /private/evidence/behavioral-workspace/workspace.json
```

The workspace snapshots the target config, creates one private run directory and
`session-000.json` for every frozen identity, hashes the workspace root object,
and rejects later root substitution. Inspect deterministic next actions with:

```bash
python scripts/campaign_workspace.py status \
  --workspace /private/evidence/behavioral-workspace/workspace.json \
  --output /private/evidence/behavioral-workspace/status-001.json
```

The status report classifies each run as awaiting provider capture, review export,
external review, review import, finalization, finalized, or invalid, and prints
the exact next command. It never selects a favorable subset and cannot mark the
campaign complete until every run has a replay-valid result.

For release execution, wrap every provider capture with
`scripts/attempt_inventory_cli.py`; the ordinary capture command is development
only. Human review remains governed by `evals/human-review.schema.json`,
`evals/rubric.md`, and the blinded calibration set described in
`evals/reviewer-calibration.md`.

## Current execution constraint

The repository does not treat provider quota as a software defect or fabricate a
replacement run. When provider access is unavailable, configs, workspaces, and
source packs may be prepared, but no real-model passage is claimed until the
provider returns authentic completions.



## Preserved implementation branch — 26 October 2026

The older development, persistence and release-tooling work is retained on `mac/preserve-qualification-tooling-20261026`. It diverges from current main and the later consolidated agent skill. It is a recovery/review candidate, not a qualified release or the active installed skill. The deterministic run reported five unit-test errors: the persistent-store API, three obsolete release-gate lookups, and the qualification-packet initializer. Its harness also ran from a dirty source tree and therefore did not pass its clean-source gate. All 610 synthetic automated harness cases passed, with human review still pending; these are harness checks, not authentic behavioral qualification. Reconcile useful tooling with current owners before integration.
