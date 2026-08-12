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
timezone-aware `frozen_at`, is bound to the candidate commit, and is
self-hashed before any gate execution. Private keys stay with the independent
authority. Configure exactly one authority and a distinct public key for every
role; key aliases cannot collapse independent gates. The owner distributes the
resulting `policy_sha256` to the verifier operator over an independent channel.
The packet is not trusted unless it matches that out-of-band anchor.

The committed templates do not authorize anyone. Adding hash-shaped text or
setting a status field cannot pass a gate. `scripts/release_evidence.py`
verifies the exact role, candidate commit, artifact hash, receipt chronology,
packet-unique nonce, trusted public-key hash, and Ed25519 signature with OpenSSL.
It also requires the packet's candidate to equal the exact clean Git checkout
provided to the verifier. Git and OpenSSL are trusted host dependencies; run
the verifier only on the restricted evaluation host.

## Required gates

| Gate | Required external role | Executable minimum |
|---|---|---|
| `behavioral_qualification` | behavioral evidence authority | Conditional full-suite matrix passes all automated, hard, score, agreement, Chinese-integrity, and non-inferiority rules. |
| `reviewer_attestation` | reviewer authority | At least two identities, independence, and calibration are externally verified. |
| `attempt_inventory` | attempt-log authority | Immutable inventory accounts for every attempt; no unfavorable retry is omitted. |
| `holdout` | holdout authority | Independent sealed authorship, no candidate-author access, at least 20% holdout fraction, and zero hard-gate failure. |
| `privacy_preflight` | privacy authority | Named-host storage map, encryption, no-sync boundary, backup/restore, bounded retention, correction/export/deletion, and incident response are tested with no unresolved high finding. |
| `bilingual_review` | bilingual review authority | Two fluent human reviewers, preserved meaning and safety language, zero meaning/safety failure, and per-system kappa at least 0.70. |
| `pilot` | pilot authority | 10–20 consented episodes over 28–56 days; withdrawals and deletion honored; zero privacy incident, hard safety failure, dependence failure, or fabricated-persistence failure. |
| `independent_release_review` | independent release reviewer | Complete review, zero unresolved finding, explicit `APPROVE`. |
| `owner_promotion` | owner | Explicit `PROMOTE` referencing the exact artifact hashes of every preceding gate. |

No average or soft score can waive a hard failure. A signed `FAIL` or
`INVALIDATED` artifact must contain at least one reason in `hard_failures` and
returns the whole release to `BLOCKED`.

## Gate artifacts and receipts

A gate artifact follows `release/gate-artifact.schema.json`. Calculate its
`artifact_sha256` over canonical JSON with that field omitted. The authority
then signs the canonical `payload` from
`release/signed-receipt.schema.json`; the payload binds the gate, candidate,
artifact hash, outcome, issuance time, and a packet-unique nonce. The verifier
does not claim a global replay registry outside the packet.

An example signing operation, performed outside this repository, is:

```text
openssl pkeyutl -sign -inkey private-ed25519.pem -rawin \
  -in canonical-receipt-payload.json -out receipt.sig
```

Base64-encode `receipt.sig` into `signature_base64`. Put the artifact, receipt,
trusted public keys, policy, and evidence index in one access-controlled packet
directory. Use relative non-symlink paths and then run:

```text
python scripts/release_evidence.py \
  --index /private/release-packet/evidence-index.json \
  --policy /private/release-packet/trust-policy.json \
  --expected-policy-sha256 OWNER_DISTRIBUTED_64_HEX_HASH \
  --repository /path/to/clean/candidate-checkout
```

`qualification_update_allowed` becomes true only for a cryptographically valid
`PROMOTED` packet. The verifier never edits `release/qualification.json`,
installs the skill, registers it in a catalog, or enables implicit invocation.
Those remain separate owner-controlled actions after review.

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
