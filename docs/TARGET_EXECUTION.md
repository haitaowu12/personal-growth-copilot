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
  model/version, settings, declared tools, skill, and a named environment
  allowlist. The original pathname cannot be swapped after validation.
- The freeze config is required to be secret-free. The builder and validator
  reject common secret-bearing key names, but cannot infer every arbitrary
  plaintext value; inspect the freeze before use. At execution, only explicitly
  allowlisted environment names may cross into the adapter process. Runtime and
  loader control names such as `PATH`, `PYTHONPATH`, `LD_*`, and `DYLD_*` are
  rejected.
- The suite, both baseline definitions, selected cases, and every
  case/system/variant/repetition identity are frozen in a complete run plan.
- Every completion is bound to the exact request and provider identity.
- The session pauses after each completion. It cannot choose its next branch
  until a two-reviewer label packet with an opaque blinded run ID is imported.
- Reviewer IDs must appear in the frozen roster, system identity is omitted from
  the review packet, and Chinese cases require rostered fluency. Fake consensus
  is rejected; a disagreement requires a third rostered reviewer. The current
  `external_pending` state does not cryptographically prove the reviewers'
  real-world identities or independence and therefore cannot complete a human
  review release gate.
- Human hard failures remain hard failures. Scores cannot average them away.
- Dimension/overall score floors and weighted-kappa agreement are calculated;
  a low-scoring or low-agreement run has development quality status `fail` even
  when automated safety gates pass.
- Finalization deterministically replays the captured path through the same
  safety, resource, memory, branch, and hard-gate runtime used by conformance.

## Adapter protocol

The executable reads exactly one JSON object from standard input and writes
exactly one JSON object to standard output. It receives:

- protocol `pgc-stdio-v1`;
- frozen provider-identity SHA-256;
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
   languages, and the SHA-256 of an externally retained independence
   attestation. Then build the config:

   ```text
   python scripts/build_target_config.py \
     --adapter /absolute/path/to/adapter \
     --adapter-version <version> \
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

4. Review the completion using the opaque `blinded_run_id` and
   `evals/human-review.schema.json`; do not give reviewers the session or target
   config. Import the packet into another new state file:

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
behavioral comparison. Never retain only favorable runs. Keep provider response
identifiers, external reviewer-role attestations, agreement analysis, and all
failed examples. Store evaluation transcripts under the approved restricted
evidence path, not in the user dossier or repository.
