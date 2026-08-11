# Record-store contract

Use `scripts/record_store.py` as the non-persistent conformance target. It does
not authorize a real database, cloud memory, sync path, or sensitive-state
initialization.

## Required operation sequence

1. Build a candidate record that passes the canonical Draft 2020-12 schema and
   semantic integrity checks.
2. Produce an exact preview bound to the current revision, purpose, proposed
   revision, and expiry.
3. Show the preview to the user through the host.
4. Let a trusted host verifier attest an affirmative user action. Reject an
   arbitrary model- or caller-created string as confirmation.
5. Issue at most one active token for that preview. Bind it to the opaque,
   single-use host attestation and store-owned clock.
6. Commit atomically only when the preview, token, expiry, and base revision
   still match.
7. Return the actual opaque revision and minimized audit-event identifiers.

Generate `record_id`, preview, attestation, consent, revision, and audit IDs as
opaque values. Never place a name, email, account identifier, purpose text, or
other user content in an identifier. The canonical record requires
`gr_` followed by 32 lowercase hexadecimal characters; host attestations require
`att_` followed by 32 lowercase hexadecimal characters.

Never reinterpret silence, general use, or a prior session as write consent.
Never reuse a token or host attestation. A revoked, expired, consumed, or stale
token must fail without changing the record. Revocation cancels the complete
preview and its token family. Use a store-owned clock; do not accept a caller's
claimed current time.

## Corrections

Preview corrections like any other write. Keep the prior revision available
until the user separately requests deletion. Link the correction to an existing
item. Mark supported targets as superseded, and do not let superseded content
continue to influence advice. Reject a target class when the schema cannot
express an unambiguous replacement, removal, or supersession.

## Export and deletion

Return an inspectable copy and content hash for export. A deletion operation
must identify the complete record, require its own exact-preview consent, erase
all content-bearing revisions and pending previews, and report whether content
remains. Callers must discard their displayed preview copies. Minimized
audit metadata may remain only under a disclosed retention rule; it must not
duplicate the personal content.

## Persistent-host gate

Before implementing or enabling a persistent adapter, record and review:

- data flow, processor, model-provider, egress, and logging paths;
- local-only versus sync behavior and exact storage and backup locations;
- encryption in transit and at rest, keys, access boundary, and recovery path;
- purpose, retention, export, correction, deletion, backup-erasure, and
  incident responsibilities;
- the user-facing disclosure and proof returned by each operation.

Fail closed if any required host capability or deletion guarantee is unknown.
