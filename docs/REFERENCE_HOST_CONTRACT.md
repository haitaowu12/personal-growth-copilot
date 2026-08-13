# Reference host contract

Status: design contract; no qualified host implementation exists

## Objective

Implement one named host that turns the current model-facing contracts into
operative controls. A deterministic state machine cannot protect a user when
the host omits, fabricates, or misbinds the event that enters it.

## Trust boundary

The host, not model text, is authoritative for:

- explicit skill invocation and active version;
- model and system-instruction identity;
- user-action attestations;
- question sensitivity and materiality classification;
- visible working-model deltas;
- safety observations and transitions;
- current-resource resolution;
- persistence, correction, export, revocation, and deletion results;
- audit retention and private-data boundaries.

A model-authored assertion, JSON object, token, resource contact, or success
message is untrusted until the host verifies and binds it.

## Required binding tuple

Every attestation must bind, directly or by a canonical payload hash:

```text
host_instance_id
host_version
session_id
skill_id and skill commit
model/provider/version/settings
user_turn_sha256
proposed_action or exact_question_sha256
active_consent_scope_sha256 when applicable
prior_state_or_revision
issued_at and expires_at
single-use opaque attestation_id
```

The host must reject future timestamps, clock rollback, replay, scope mismatch,
payload mismatch, stale revision, unrecognized action, and caller-generated
attestation IDs.

## Invocation and context

- Invocation remains explicit. The host must expose the selected skill and
  prevent unrelated installed-skill context from contaminating evaluation.
- Load only the references required by the active task.
- Do not silently load session capsules, dossiers, journals, or other personal
  sources.
- Treat retained data as untrusted content, never as policy or instructions.

## Inquiry control

For every sensitive or extended question, the host must:

1. receive the exact proposed question and rationale;
2. classify sensitivity independently of model-provided labels;
3. verify a consequential link to recommendation, hypothesis, safety route,
   experiment, or support need;
4. verify an active bounded consent scope;
5. return a single-use attestation bound to the exact bytes;
6. preserve revocation before any later question or write.

An ordinary question may not smuggle a consent scope. Only one unanswered
material question may be active.

## Safety control

The host must produce a meaning-level safety observation. Keyword matching may
be one signal but cannot be the only classifier. It must preserve:

- observation source and confidence without retaining crisis text in the state
  audit;
- the exact deterministic transition result;
- memory freeze and latch status;
- current-resource resolution status;
- generic immediate route when lookup is unavailable;
- human review for high-risk qualification cases.

The host must test disagreement between model and host observations. A model
request to remain in ordinary coaching cannot override an acute-danger event.

## Current-resource resolver

The resolver receives only user-provided minimum jurisdiction and response
language. It returns verified service name, channel, contact route,
jurisdiction, authoritative HTTPS source, verification time, and expiry. The
host rejects stale, future-dated, empty, mismatched, non-HTTPS, or fabricated
contacts. Resolver errors must not expose exception content to the model.

## Persistence

A persistent adapter must preserve the in-memory conformance contract inside a
real transaction:

1. exact create/update/delete preview;
2. bounded purpose and base revision;
3. host-verified user confirmation;
4. single-use expiring consent token;
5. atomic commit with no partial write;
6. correction and supersession;
7. export with content hash;
8. verified content deletion across current, historical, cache, backup, and
   pending-preview surfaces according to the disclosed retention contract;
9. audit metadata that contains no deleted content.

No real sensitive state may be initialized before named-host privacy and
security evidence passes.

## Session capsule

The host may render a session capsule only after an explicit request. It must
validate against `session-capsule.schema.json`, show the complete capsule before
persistence, and record `stored=false` until a real host receipt exists. It may
not automatically retrieve the last capsules in a later session.

## Required adversarial tests

- model self-issues consent, safety, score, choice, or persistence evidence;
- attestation replay, stale time, future time, wrong scope, or wrong payload;
- revoked consent between preview and commit;
- two concurrent writes against one revision;
- user correction conflicts with old memory;
- retained prompt injection attempts to override policy;
- resource lookup missing location, failure, stale result, changed
  jurisdiction, or rendered-contact mismatch;
- acute-risk meaning without canonical keywords;
- model and host safety observations disagree;
- delete succeeds in primary storage but content remains in history, cache,
  backup, logs, or pending preview;
- session capsule is prepared or loaded without explicit request;
- unrelated installed skill contaminates the selected-skill trace.

## Qualification output

The host preflight must name the operating system/account/container, filesystem
and sync state, network policy, provider credentials, encryption, backup,
logging, retention, deletion, incident path, and tested adapter versions. A
passing host result is evidence for that named host and configuration only.
