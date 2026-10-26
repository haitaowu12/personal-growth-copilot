# Privacy-gated persistent record store

## Boundary

`record_store.py` remains the host-neutral in-memory contract. The optional
`persistent_record_store.py` adapter adds crash-safe local persistence while
preserving preview, exact-delta consent, atomic commit, revision, correction,
revocation, export, and complete logical deletion semantics.

The adapter is present but **disabled by default**. Its existence does not grant
permission to persist personal data. Activation requires all of the following:

1. a current configured release trust policy;
2. a current `PASS` privacy-preflight gate in the independently anchored evidence
   index;
3. a privacy-host identity bound to the owner-frozen policy;
4. a signed, time-bounded persistence authorization from the configured privacy
   authority for the exact candidate, evidence index, privacy artifact, named
   host, environment, and storage-root filesystem object; and
5. a host verifier that validates that signature and current release anchors.

The model cannot create or verify this authorization.

## Storage invariants

- absolute, non-symlink, current-user-owned mode-`0700` storage root;
- mode-`0600` canonical JSON state and lock files;
- no-follow, bounded reads and self-hashed state;
- exclusive file locking across processes;
- write-to-private-temporary, `fsync`, atomic replacement, and directory `fsync`;
- stale preview/revision rejection after concurrent updates;
- no raw user content in the audit ledger;
- bounded audit retention from 1 through 365 days; and
- deletion of current content, historical revisions, pending previews, consent
  tokens, and attestation content from the logical store.

Filesystem encryption, backup scope and erasure, no-sync placement, media
sanitization, account isolation, and incident response remain host controls.

## Invented-data host drill

Run the lifecycle drill only in a dedicated empty private directory:

```bash
mkdir -m 700 /private/pgc-drill
python scripts/run_persistent_store_drill.py \
  --storage-root /private/pgc-drill \
  --named-host <host> \
  --environment-id <stable-environment-id> \
  --audit-retention-days 30 \
  --output /private/evidence/privacy/persistent-store-drill.json
```

The drill uses invented fixture data and exercises authorization rejection,
create/restart, exact export, correction/restart, deletion/restart, bounded audit
retention, and cleanup. It produces no privacy `PASS`; its receipt becomes one
source file for the independent privacy audit.

## External privacy source and authorization

The privacy authority supplies the seven control observations and evidence files.
The repository derives their hashes and witness payload:

```bash
python scripts/external_source_builder.py prepare-privacy-source \
  --host-identity /private/evidence/privacy/host-identity.json \
  --checks /private/evidence/privacy/checks.json \
  --findings /private/evidence/privacy/findings.json \
  --retention-days 30 \
  --completed-at <time> \
  --nonce <unique-nonce> \
  --output /private/evidence/privacy/privacy-signing-request.json
```

After the independent audit witness signs the exact payload, assemble and verify
the source. Once that source has produced a current signed privacy gate, prepare
a separate persistence-authorization request:

```bash
python scripts/persistence_authorization.py prepare \
  --index /private/evidence/evidence-index.json \
  --policy /private/evidence/trust-policy.json \
  --host-identity /private/evidence/privacy/host-identity.json \
  --storage-root /private/pgc-records \
  --expected-policy-sha256 <owner-policy-hash> \
  --expected-index-sha256 <owner-current-index-hash> \
  --authorization-id pauth_<32-hex> \
  --issued-at <time> --expires-at <time> \
  --nonce <unique-nonce> \
  --output /private/evidence/privacy/persistence-authorization-request.json
```

The privacy authority signs that payload. `assemble` verifies the Ed25519
signature and creates the artifact consumed by
`SignedPersistenceAuthorizationVerifier`. A stale index, failed privacy gate,
wrong storage root, wrong authority, changed candidate, expired authorization,
or bad signature fails closed.

