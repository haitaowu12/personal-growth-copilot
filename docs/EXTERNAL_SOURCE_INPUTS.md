# External source input contracts

`scripts/external_source_builder.py` accepts declaration files from external
roles and derives all paths, file hashes, coverage, use counts, ledgers, witness
payloads, and source manifests. Declaration files are not evidence by themselves.
Every referenced file must already exist inside the packet root and must have
been created by the responsible independent role.

Private keys are never accepted. `prepare-*` commands create canonical signing
requests; the external witness signs the request payload outside the candidate
workspace; `assemble-*` verifies the returned Ed25519 signature.

## Reviewer declarations

```json
{
  "reviewers": [
    {
      "reviewer_id": "reviewer-0123456789abcdef",
      "languages": ["en", "zh"],
      "identity_evidence_path": "review/reviewer-1-identity.json",
      "independence_evidence_path": "review/reviewer-1-independence.json",
      "calibration_evidence_path": "review/reviewer-1-calibration.json",
      "calibrated_at": "2026-09-01T00:00:00Z",
      "identity_verified": true,
      "independence_verified": true,
      "calibration_passed": true
    }
  ]
}
```

The builder derives `subject_sha256` from the identity attestation and derives
actual use counts from the exact result manifest. Declared reviewer IDs must
equal the complete used set; extra, missing, or duplicate reviewers fail.

## Holdout authors

```json
{
  "authors": [
    {
      "author_id": "author-0123456789abcdef",
      "subject_sha256": "<64-hex>",
      "identity_evidence_path": "holdout/author-1-identity.json",
      "independence_evidence_path": "holdout/author-1-independence.json",
      "authorship_evidence_path": "holdout/author-1-authorship.json",
      "independence_verified": true
    }
  ]
}
```

The holdout seal additionally binds encrypted case bytes, exact case IDs, public
suite count, case schema, witness public key, seal time, and candidate commit.

## Holdout access events

```json
{
  "events": [
    {
      "event_id": "access-0000000000000001",
      "actor_role": "execution_role",
      "accessed_at": "2026-09-02T00:00:00Z",
      "evidence_path": "holdout/access-1.json"
    }
  ]
}
```

Candidate-author access invalidates the holdout claim. An empty event list is
valid only when the retained access system independently proves there was no
access.

## Holdout attempt events

```json
{
  "events": [
    {
      "attempt_id": "attempt-0123456789abcdef0123456789abcdef",
      "occurred_at": "2026-09-03T00:00:00Z",
      "outcome": "PASS"
    }
  ]
}
```

Events remain in chronological sequence. The builder links each event to the
previous hash, binds successful attempts to the exact case result, and creates
the witness payload. Failed or aborted attempts must not be removed.

## Privacy checks

```json
{
  "checks": [
    {
      "check_id": "storage_map",
      "status": "PASS",
      "executed_at": "2026-09-04T00:00:00Z",
      "evidence_path": "privacy/storage-map.json"
    }
  ]
}
```

The exact required control IDs are:

- `storage_map`;
- `encryption`;
- `no_sync`;
- `backup_restore`;
- `correction_export_deletion`;
- `bounded_retention`; and
- `incident_response`.

The final verifier rejects missing, extra, duplicate, failed, or unknown
controls even if the witness signed the ledger.

## Privacy findings

```json
{
  "findings": [
    {
      "finding_id": "finding-0000000000000001",
      "severity": "medium",
      "status": "RESOLVED",
      "evidence_path": "privacy/finding-1.json"
    }
  ]
}
```

Unresolved high or critical findings block the privacy gate.

## Pilot episodes

```json
{
  "episodes": [
    {
      "episode_id": "episode-0000000000000001",
      "scheduled_at": "2026-09-05T00:00:00Z",
      "closed_at": "2026-09-05T01:00:00Z",
      "outcome": "COMPLETED",
      "consent_evidence_path": "pilot/episode-1-consent.json",
      "episode_evidence_path": "pilot/episode-1.json",
      "withdrawal_requested_at": null,
      "withdrawal_honored_at": null,
      "deletion_requested": false,
      "deletion_completed_at": null
    }
  ]
}
```

Episode IDs must equal the preregistered schedule. Withdrawal and deletion
timestamps must agree with outcome and chronology. Missing or non-attempted
episodes remain explicit records rather than disappearing.

## Pilot incidents

```json
{
  "incidents": [
    {
      "incident_id": "incident-0000000000000001",
      "category": "privacy",
      "severity": "high",
      "detected_at": "2026-09-06T00:00:00Z",
      "evidence_path": "pilot/incident-1.json"
    }
  ]
}
```

Privacy, hard-safety, dependence, and fabricated-persistence incidents are
preregistered stop categories. A critical uncategorized incident also blocks
promotion.

## Signature handoff

Each signing request contains:

- domain-separated canonical payload;
- candidate commit;
- externally configured public-key path and SHA-256;
- unsigned source or ledger artifact; and
- request self-hash.

The signer returns only canonical base64 signature bytes. The assembler reloads
the bound public key, verifies the signature, validates the complete source
schema, and writes a new artifact. A changed request, key, payload, file, event
count, or candidate fails closed.

