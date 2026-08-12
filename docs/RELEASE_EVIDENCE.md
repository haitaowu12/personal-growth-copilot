# Release evidence and promotion

The release gate is a signed evidence workflow, not a checklist that a model or
run operator can mark complete. The repository ships with
`release/trust-policy.json` in `UNCONFIGURED` state and
`release/evidence-index.json` in `BLOCKED` state. Do not store private signing
keys, private pilot content, reviewer identities, or holdout plaintext here.

## Freeze and trust setup

After the candidate commit is frozen, the owner prepares a trust policy in a
restricted evidence directory. Each authority has a public Ed25519 key, a
single role and exactly one gate that role may attest. The policy records a
timezone-aware `frozen_at`, is bound to the candidate commit and one unique
`attempt_campaign_id`, and is self-hashed before any gate execution. It also
freezes the exact target-config hash, the independently prepared holdout-seal
hash, the named privacy-host identity hash, and the preregistered pilot-protocol
hash. A later config, holdout set, host, or pilot plan cannot be substituted
under the same release epoch. That
campaign epoch is the only attempt chain accepted for the candidate; changing
the id cannot reset a failure or retry history. Private keys stay with the
independent authority. Configure exactly one authority and a distinct public
key for every role; key aliases cannot collapse independent gates. The owner distributes the
resulting `policy_sha256` and current `index_sha256` to the verifier operator
over an independent, current-state channel. The packet is not trusted unless it
matches both anchors. Replacing or invalidating evidence requires a new index
hash, and the current-state channel must replace the prior index anchor.

Build the configured policy from its actual preregistered sources rather than
typing their hashes into JSON. `holdout-seal.json` must already be prepared by
the independent holdout author before this freeze and conform to
`release/holdout-seal.schema.json`; its self-hash is what the policy binds.

```text
python scripts/release_packet.py build-trust-policy \
  --packet-root /private/release-packet \
  --config /private/release-packet/target/target-config.json \
  --holdout-seal /private/release-packet/holdout/holdout-seal.json \
  --privacy-host-identity /private/release-packet/privacy/host-identity.json \
  --pilot-protocol /private/release-packet/pilot/protocol.json \
  --authorities /private/release-packet/authorities/authority-roster.json \
  --attempt-campaign-id campaign-2026-08-12-001 \
  --output /private/release-packet/trust-policy.json
```

The resulting policy also binds the exact self-hashed qualification plan, so
the candidate, campaign epoch, preregistration input paths, and fixed policy
destination cannot be changed after freeze. The authority roster contains only
`authorities`; each entry supplies a unique
`key_id`, one release role, and a packet-relative Ed25519 public-key path. The
builder reads, canonicalizes, and hashes the exact config, seal, host identity,
pilot protocol, and nine distinct public keys before emitting a create-only
policy. The owner distributes that exact policy hash out of band.

The committed templates do not authorize anyone. Adding hash-shaped text or
setting a status field cannot pass a gate. `scripts/release_evidence.py`
verifies the exact role, candidate commit, artifact hash, receipt chronology,
packet-unique nonce, trusted public-key hash, and Ed25519 signature with OpenSSL.
It also requires the packet's candidate to equal the exact clean Git checkout
provided to the verifier. Git and OpenSSL are trusted host dependencies; run
the verifier only on the restricted evaluation host.

## Read-only named-host discovery

Before creating a privacy source manifest or implementing a persistent record
adapter, capture a bounded discovery report on the intended evaluation host.
The output parent must already be a current-user-owned mode-`0700` directory
outside the source repository, on the home filesystem, with no macOS access
control list or symlink component; the report is created once with mode `0600`.

```text
python scripts/host_privacy_discovery.py \
  --storage-root /private/release-packet \
  --named-host restricted-local-host \
  --environment-id pgc-private-evaluation-001 \
  --sync-root /known/sync/root \
  --output /private/release-packet/privacy/host-discovery.json
```

The command deliberately exits nonzero with `NOT_READY`. It hashes rather than
retains raw command output, reports unavailable or ambiguous controls as
`UNKNOWN`, and reports an unconfigured backup destination or invalid storage
boundary as `FAIL`. Do not pass `--sync-inventory-complete` unless an authorized
host operator has established that the supplied sync-root list is the complete
bounded inventory; an unavailable declared root remains `UNKNOWN` even with
that flag. The report can never set `privacy_gate_ready` or
`persistent_adapter_authorized` to true and is not a substitute for the
source-witnessed privacy-preflight gate below.

Initialize the restricted packet outside the source repository and any synced
folder. This command creates only mode-`0700` directories and a mode-`0600`,
self-hashed draft plan. It does not create or impersonate reviewers, holdout
authors, authorities, witnesses, host controls, participants, evidence, or
private keys:

```text
python scripts/qualification_packet.py init \
  --packet-root /private/release-packet \
  --attempt-campaign-id campaign-2026-08-12-001
```

Place the real externally controlled inputs at the packet-relative locations
recorded in `qualification-plan.json`, keeping every private key outside the
packet and candidate-author access. Then run:

```text
python scripts/qualification_packet.py preflight \
  --packet-root /private/release-packet
```

Until every real input exists and passes the same validation used by
`build-trust-policy`, preflight exits nonzero with `NOT_READY`. It rejects a
different or dirty candidate checkout, path or permission escape, symlinks,
detectable PEM private-key material, an existing policy output, invalid source
schemas/hashes/times, noncanonical target config, incomplete run scope, and
aliased witness or authority key material. Each declared input is reported as
`MISSING`, `INVALID`, or `VALID`, with bounded validation errors for an invalid
input, even while other inputs remain missing. Cross-input key independence,
chronology, and the complete frozen bindings are still checked only through the
combined policy preparation. `READY_TO_FREEZE` is only permission to execute
the create-only trust-policy builder; it is not gate evidence or a release
claim.

The policy builder independently repeats the packet-permission, symlink,
private-key-marker, plan, path, candidate, campaign, and preregistration input
checks at the authoritative freeze boundary. Skipping the convenience preflight
therefore cannot bypass those controls.

## Required gates

| Gate | Required external role | Executable minimum |
|---|---|---|
| `behavioral_qualification` | behavioral evidence authority | Conditional full-suite matrix passes all automated, hard, score, agreement, Chinese-integrity, and non-inferiority rules. |
| `reviewer_attestation` | reviewer authority | At least two identities, independence, and calibration are externally verified. |
| `attempt_inventory` | attempt-log authority | Externally witnessed immutable inventory accounts for every attempt, binds the preregistered full run plan and verified result files, proves provider-access and artifact-inventory audit hashes, and omits no unfavorable retry. |
| `holdout` | holdout authority | Independent sealed authorship, no candidate-author access, at least 20% holdout fraction, and zero hard-gate failure. |
| `privacy_preflight` | privacy authority | Named-host storage map, encryption, no-sync boundary, backup/restore, bounded retention, correction/export/deletion, and incident response are tested with no unresolved high finding. |
| `bilingual_review` | bilingual review authority | Two fluent human reviewers, preserved meaning and safety language, zero meaning/safety failure, and per-system kappa at least 0.70. |
| `pilot` | pilot authority | 10–20 consented episodes over 28–56 days; withdrawals and deletion honored; zero privacy incident, hard safety failure, dependence failure, or fabricated-persistence failure. |
| `independent_release_review` | independent release reviewer | Complete review, zero unresolved finding, explicit `APPROVE`. |
| `owner_promotion` | owner | Explicit `PROMOTE` referencing the exact artifact hashes of every preceding gate. |

No average or soft score can waive a hard failure. A signed `FAIL` or
`INVALIDATED` artifact must contain at least one reason in `hard_failures` and
returns the whole release to `BLOCKED`.

The independent review artifact must execute after every preceding gate receipt
and reference those seven exact artifact hashes. Owner promotion must execute
after the independent-review receipt and reference all eight prerequisite
artifact hashes.

## Gate artifacts and receipts

A gate artifact follows `release/gate-artifact.schema.json`. Calculate its
`artifact_sha256` over canonical JSON with that field omitted. The authority
then signs the canonical `payload` from
`release/signed-receipt.schema.json`; the payload binds the gate, candidate,
artifact hash, outcome, issuance time, and a packet-unique nonce. The verifier
does not claim a global nonce registry; stale-packet rejection depends on the
owner's independently distributed current `index_sha256`.

For this protocol, “canonical JSON” means UTF-8 output equivalent to Python
`json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
allow_nan=False)`, with no trailing newline. Integers and decimal values must
retain the schema-valid JSON type used in the artifact. Producers in another
language must reproduce those exact bytes before hashing or signing.

Use `scripts/release_packet.py` to construct create-only canonical artifacts,
receipt payloads, signed-receipt envelopes, and evidence-index versions. The
behavioral and attempt builders replay their exact campaign and witnessed
inventory sources. A passing reviewer, holdout, privacy, bilingual, or pilot
gate must use `build-source-artifact`; its derived assertions, source-manifest
path, source hash, and every bounded retained evidence file are replayed again
by the final release verifier. The generic external builder cannot emit PASS
for those five gates. It remains available for their signed FAIL/INVALIDATED
records and for independent-review and owner decisions. Independent review and
owner artifacts derive their prerequisite references from an already verified,
out-of-band-anchored prior index.

## Replayable external source packs

All source packs conform to `release/external-gate-source.schema.json`, live in
the restricted packet directory, bind the exact candidate commit, and complete
no earlier than the owner-frozen trust policy. Preregistered inputs—the holdout
seal, reviewer calibration, named-host identity, and pilot protocol—may and in
the applicable cases must predate the policy; their exact hashes are frozen by
it before qualification execution. The holdout seal, privacy-host identity,
and pilot protocol each bind a distinct Ed25519 witness public key. Keep every
corresponding private key outside the packet and candidate-author access.
Referenced paths are relative,
bounded regular files; absolute paths, symlinks, traversal, missing files, and
hash changes fail closed. Private identity, holdout, host, and pilot evidence
belongs in this restricted directory, never in the repository.

- Reviewer packs bind the exact target config and result manifest, reconcile
  every reviewer actually used, reject two pseudonyms for one stable subject,
  require calibration before the first submitted qualification label, and
  bind a structured, self-hashed identity attestation plus independence and
  calibration evidence to the frozen roster and calibration set.
- Holdout packs derive the holdout fraction from the public and sealed case
  counts, require exact result coverage of the sealed case IDs, preserve access
  audit, encrypted case, schema, author, raw transcript, result, and chained
  attempt-event files, verify the preregistered holdout-witness signature over
  every attempt head and count, and fail on candidate-author access, an omitted
  or failed attempt, transcript tampering, or any hard-gate code.
- Privacy packs require the named-host identity plus the fixed storage-map,
  encryption, no-sync, backup/restore, correction/export/deletion, bounded-
  retention, and incident-response evidence files. The exact catalog and full
  findings ledger are hash/count bound by the preregistered host-audit key;
  check results and open or accepted high/critical findings determine the
  assertions. Extra controls cannot hide a failure.
- Bilingual packs replay the reviewer pack and its exact target results,
  enumerate every Chinese or mixed-language turn review, require verified
  fluent reviewers, reproduce both primary score vectors and translation
  failure codes, and recalculate per-system weighted kappa. Missing runs,
  altered labels, degenerate agreement, or kappa below `0.70` fail.
- Pilot packs bind an owner-frozen protocol and exact 10–20 episode schedule,
  preserve consent and episode records, verify a preregistered witness signature
  over the complete episode/incident ledger, derive elapsed days from the first
  scheduled episode through the last closed episode, reconcile every scheduled
  episode, and derive withdrawal, deletion, privacy, safety, dependence, and
  fabricated-persistence outcomes from that ledger. Out-of-window actions and
  high/critical uncategorized incidents fail closed.

After the authority prepares a complete source pack, build its artifact from
that source rather than from a hand-written assertion file:

```text
python scripts/release_packet.py build-source-artifact \
  --gate privacy_preflight \
  --source /private/release-packet/privacy/source.json \
  --packet-root /private/release-packet \
  --policy /private/release-packet/trust-policy.json \
  --expected-policy-sha256 OWNER_DISTRIBUTED_POLICY_HASH \
  --output /private/release-packet/privacy-preflight.artifact.json
```

Use the same command for `reviewer_attestation`, `holdout`,
`bilingual_review`, and `pilot`. The relevant external authority must still
inspect the semantic quality of the retained evidence and sign the resulting
artifact; source replay does not turn machine-readable files into proof of
real-world identity, independence, host control, or consent without that role.

```text
python scripts/release_packet.py build-attempt-artifact \
  --config /private/evidence/target-config.json \
  --index /private/evidence/attempt-ledger/index-FINAL.json \
  --manifest /private/evidence/result-manifest.json \
  --policy /private/release-packet/trust-policy.json \
  --expected-policy-sha256 OWNER_DISTRIBUTED_POLICY_HASH \
  --expected-head-sha256 WITNESS_DISTRIBUTED_CURRENT_HEAD \
  --expected-event-count WITNESS_DISTRIBUTED_CURRENT_COUNT \
  --output /private/release-packet/attempt-inventory.artifact.json

python scripts/release_packet.py build-receipt-payload \
  --artifact /private/release-packet/attempt-inventory.artifact.json \
  --nonce AUTHORITY_UNIQUE_NONCE \
  --output /private/release-packet/attempt-inventory.payload.json
```

The authority signs the exact payload bytes outside the candidate/operator
environment:

```text
openssl pkeyutl -sign -inkey private-ed25519.pem -rawin \
  -in canonical-receipt-payload.json -out receipt.sig
```

Keep `receipt.sig` as raw signature bytes. Put the artifact, signature, trusted
public keys, policy, and evidence index in one access-controlled packet
directory. The builder verifies the signature against the configured role key,
encodes it in the receipt envelope, and advances only an anchored prior index:

```text
python scripts/release_packet.py assemble-receipt \
  --payload /private/release-packet/attempt-inventory.payload.json \
  --signature /private/release-packet/receipt.sig \
  --key-id CONFIGURED_ATTEMPT_AUTHORITY_KEY_ID \
  --policy /private/release-packet/trust-policy.json \
  --expected-policy-sha256 OWNER_DISTRIBUTED_POLICY_HASH \
  --output /private/release-packet/attempt-inventory.receipt.json

python scripts/release_packet.py advance-index \
  --prior-index /private/release-packet/evidence-index-v2.json \
  --artifact /private/release-packet/attempt-inventory.artifact.json \
  --receipt /private/release-packet/attempt-inventory.receipt.json \
  --policy /private/release-packet/trust-policy.json \
  --expected-policy-sha256 OWNER_DISTRIBUTED_POLICY_HASH \
  --expected-index-sha256 OWNER_DISTRIBUTED_CURRENT_INDEX_HASH \
  --output /private/release-packet/evidence-index-v3.json
```

Distribute the new index hash as the replacement current-state anchor. Then
verify the packet with relative non-symlink paths:

```text
python scripts/release_evidence.py \
  --index /private/release-packet/evidence-index.json \
  --policy /private/release-packet/trust-policy.json \
  --expected-policy-sha256 OWNER_DISTRIBUTED_POLICY_HASH \
  --expected-index-sha256 OWNER_DISTRIBUTED_CURRENT_INDEX_HASH
```

Run that command from the exact candidate checkout using the verifier contained
in that checkout. The CLI rejects a dirty checkout and rechecks the source after
verification; it does not accept a separate verifier/candidate repository pair.

`qualification_update_allowed` becomes true only for a cryptographically valid
`PROMOTED` packet. The verifier never edits `release/qualification.json`,
installs the skill, registers it in a catalog, or enables implicit invocation.
Those remain separate owner-controlled actions after review.

For the `attempt_inventory` gate, the specialized builder reruns full inventory
verification directly from the ledger, exact result files/manifest, configured
policy, and independently supplied witness head/count. Its artifact's primary
`evidence_refs` entry is the resulting exact `inventory_sha256`; the remaining
references include the provider-access control/audit hash and complete
artifact-inventory hash reported by that verifier. The attempt authority signs only after obtaining the
current witness head and count independently and confirming that all seven
attempt assertions required by `scripts/release_evidence.py` are true. A local
list of submitted result files, an operator-set boolean, or a stateless signer
does not satisfy this gate.

## Holdout handling

Freeze the candidate before independent authors receive their brief. Keep
plaintext and decryption keys outside candidate-author access. The holdout
artifact records only sealed counts, fraction, ciphertext/schema hashes,
author-role evidence, access-audit evidence, execution results, and any
invalidation. Candidate-author access, a changed ciphertext, a missing attempt,
or early disclosure invalidates the gate and requires a new seal.

## Privacy preflight

Test the actual named host, not an abstract architecture. Evidence must cover:

- every storage, log, cache, backup, sync, analytics, and model-provider route;
- encryption and key ownership in transit and at rest;
- prevention of consumer sync or unintended backup for sensitive records;
- data minimization and prohibited raw-content enforcement;
- exact preview/consent/commit semantics and authoritative write results;
- correction, export, deletion, backup deletion, and retention expiry;
- access control, credential isolation, audit minimization, incident response,
  and a recovery drill;
- the provider's data-use and retention contract for the chosen account.

Persistent storage and a real private pilot remain prohibited until this gate
passes.

## Pilot and invalidation

Pilot participants receive explicit boundaries, data-use disclosure, stop and
withdrawal rights, and a named incident contact. Preserve every scheduled
episode and withdrawal; do not select favorable sessions. Any privacy incident,
critical hard-gate failure, dependence/exclusivity behavior, or fabricated
persistence claim fails the pilot gate. Corrective changes invalidate the
candidate evidence and require a new candidate freeze and applicable reruns.
