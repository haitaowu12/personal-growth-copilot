# Authored target execution

This workflow captures target and matched-baseline behavior. The stdio request
does not contain expected events, forbidden labels, branches, or rubric scores.
That protocol property is not an OS isolation claim: the trusted adapter keeps
the ambient filesystem and network rights of its host process. It produces
development evidence only until the full authored suite,
reviewer agreement, acceptance rules, untouched holdouts, privacy gate, and
pilot gates pass.

## Trust boundaries

- The provider is snapshotted byte-for-byte into a private temporary directory,
  invoked without a shell, and bound to its SHA-256, source commit,
  model/version, settings, declared tools, skill, exact inference-runtime
  executable hash, and a named environment allowlist. The Codex adapter reads,
  hashes, snapshots, and executes the same runtime bytes; profile and result
  files are likewise hashed and consumed from one bounded read.
- The freeze config is required to be secret-free. The builder and validator
  reject common secret-bearing key names, but cannot infer every arbitrary
  plaintext value; inspect the freeze before use. At execution, only explicitly
  allowlisted environment names may cross into the adapter process. Runtime and
  loader control names such as `PATH`, `PYTHONPATH`, `LD_*`, and `DYLD_*` are
  rejected.
- The suite, both baseline definitions, selected cases, and every
  case/system/variant/repetition identity are frozen in a complete run plan.
  Authored-target validation also binds the supplied suite to the exact
  canonical `evals/cases.json` bytes in the clean source checkout; a
  schema-valid substitute suite is rejected.
- Every completion is bound to the exact request and provider identity.
- The session pauses after each completion. It cannot choose its next branch
  until a two-reviewer label packet with an opaque blinded run ID is imported.
- Reviewer IDs must appear in the frozen roster, system identity is omitted from
  the review packet, and Chinese cases require rostered fluency. Fake consensus
  is rejected; a disagreement requires a third rostered reviewer. The current
  `external_pending` state and hash-shaped roster references do not prove the
  reviewers' real-world identities or independence and therefore cannot
  complete a human-review release gate.
- Human hard failures remain hard failures. Scores cannot average them away.
- Dimension/overall score floors and weighted-kappa agreement are calculated;
  a low-scoring or low-agreement run has development quality status `fail` even
  when automated safety gates pass.
- Finalization deterministically replays the captured path through the same
  safety, resource, memory, branch, and hard-gate runtime used by conformance.

## Adapter protocol

The executable reads exactly one JSON object from standard input and writes
exactly one JSON object to standard output. It receives:

- protocol `pgc-stdio-v2`;
- frozen provider-identity SHA-256;
- frozen secret-free host/model/settings/tool metadata plus skill, baseline,
  exact inference-runtime executable hash, and complete target/baseline
  profile-bundle hashes, so the adapter cannot silently select an unbound
  executable or model profile;
- system, case, variant, repetition, and turn identifiers;
- the current user turn and prior user/assistant history.

It does not receive expected labels or rubric content over this protocol. A
trusted adapter could still access ambient host data unless the host runs it in
a separately reviewed sandbox. Its response must echo
the request and provider hashes and provide non-empty response text, an actual
memory-write-attempt flag, structured resource claims, and an opaque provider
response identifier. Standard-output logs or extra fields fail closed.

## Freeze and execute

All commands require a clean checkout at the exact configured commit. Output
files are create-only with mode `0600`; use a new path for every state. Run the
adapter in a separately reviewed restricted account/container before using real
provider credentials or private prompts; the stdio wrapper itself is not a
sandbox and `tool_permissions` is frozen disclosure metadata, not enforcement.

1. Put secret-free model settings in a JSON object. Prepare a reviewer-roster
   object whose only key is `reviewers`; every entry declares a pseudonymous ID,
   languages, and SHA-256 values for externally retained identity,
   independence, and completed-calibration artifacts. These are references,
   not verified evidence: the only accepted state is `external_pending` until a
   separately trusted signed-receipt workflow is implemented. Then build the config:

   ```text
   python scripts/build_target_config.py \
     --adapter /absolute/path/to/adapter \
     --adapter-version <version> \
     --runtime-executable /absolute/path/to/exact-inference-runtime \
     --host <host> --model <model> --model-version <version> \
     --settings-file /absolute/path/to/settings.json \
     --reviewer-roster-file /private/reviewer-roster.json \
     --environment-name <SECRET_ENV_NAME> \
     --output /private/evidence/target-config.json
   ```

2. Initialize one case/system/variant/repetition session:

   ```text
   python scripts/target_session_cli.py init \
     --config /private/evidence/target-config.json \
     --case-id <case> --system-id <system> --variant-id <variant> \
     --repetition <n> --output /private/evidence/session-001.json
   ```

3. Capture one model completion into a new state file:

   ```text
   python scripts/target_session_cli.py capture \
     --config /private/evidence/target-config.json \
     --session /private/evidence/session-001.json \
     --adapter /absolute/path/to/adapter \
     --env <SECRET_ENV_NAME> \
     --output /private/evidence/session-002.json
   ```

4. Export the cumulative, system-blinded review request. It contains the exact
   completion, prior turns, current structured memory/resource observations,
   event candidates without their authored expected/forbidden polarity, and
   the complete rubric-dimension list; it omits system, case, variant, and
   repetition identity. Do not give reviewers the session or target config:

   ```text
   python scripts/target_session_cli.py export-review-request \
     --config /private/evidence/target-config.json \
     --session /private/evidence/session-002.json \
     --output /private/review-queue/request-001.json
   ```

   Review using `evals/rubric.md` and `evals/human-review.schema.json`. The
   returned packet must copy the exact `completion_sha256`,
   `review_request_sha256`, and `blinded_run_id`. Import it into another new
   state file:

   ```text
   python scripts/target_session_cli.py import-review \
     --config /private/evidence/target-config.json \
     --session /private/evidence/session-002.json \
     --review /private/evidence/review-001.json \
     --output /private/evidence/session-003.json
   ```

5. Repeat capture and review until status is `COMPLETE`, then finalize and
   independently verify:

   ```text
   python scripts/target_session_cli.py finalize \
     --config /private/evidence/target-config.json \
     --session /private/evidence/session-final.json \
     --output /private/evidence/result.json

   python scripts/target_session_cli.py verify \
     --config /private/evidence/target-config.json \
     --result /private/evidence/result.json
   ```

Each finalized run says `campaign_complete: false`; integrity verification of a
single run is never proof that the preregistered matrix is complete. Complete
the entire frozen run plan and independently reconcile every identity before a
behavioral comparison. The current local filesystem workflow cannot prove that
alternate attempts were not discarded, so never retain only favorable runs and
do not call the manifest attempt-complete. Keep provider response
identifiers, external reviewer-role attestations, agreement analysis, and all
failed examples. Store evaluation transcripts under the approved restricted
evidence path, not in the user dossier or repository.

## Full-suite submitted-matrix aggregation

Place every independently verified final run for every case in the exact
governed suite under one restricted evidence
directory. Build a manifest with one `--result` argument per run; the builder
rejects missing, duplicate, extra, invalid, out-of-directory, symlinked, or
hash-mismatched results and orders them by the complete frozen run plan:

```text
python scripts/campaign_cli.py build-manifest \
  --config /private/evidence/target-config.json \
  --result /private/evidence/results/run-001.json \
  --result /private/evidence/results/run-002.json \
  --output /private/evidence/result-manifest.json

python scripts/campaign_cli.py aggregate \
  --config /private/evidence/target-config.json \
  --manifest /private/evidence/result-manifest.json \
  --output /private/evidence/campaign-result.json

python scripts/campaign_cli.py verify \
  --config /private/evidence/target-config.json \
  --manifest /private/evidence/result-manifest.json \
  --result /private/evidence/campaign-result.json
```

The aggregator refuses a selected case subset and cross-checks response-ID
uniqueness across all submitted results. The campaign artifact reports
all-system hard/automated failures, high/critical
score floors, other-case median and tenth-percentile floors, Chinese meaning
failures, per-system reviewer agreement, and paired direct-baseline
non-inferiority. It deliberately makes no benefit claim over structured
reflection without a separately preregistered paired bootstrap and
goal-authorship test. A clean submitted matrix is only `conditional_pass`.
Because this local workflow neither verifies an independent reviewer receipt
nor inventories all attempts in an immutable external system, it always emits
`campaign_complete: false`, `attempt_inventory_verified: false`, and
`evidence_status: blocked`.

The config builder's optional `--case-id` is for bounded development runs only.
Any config that does not list every governed suite case in exact suite order is
rejected by campaign aggregation.
