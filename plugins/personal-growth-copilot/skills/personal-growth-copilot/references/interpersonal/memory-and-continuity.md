# Interpersonal continuity content

[Shared continuity](../memory-and-continuity.md) and the [record-store contract](../record-store-contract.md) govern authorization and actual operations. This reference supplies case content and correction/expiry semantics, not a second host adapter. Do not auto-load a capsule or retrieve records without current bounded purpose.

Use this reference when a case continues across conversations, the user asks the
skill to remember or forget something, or repeating the same context would
materially reduce usefulness.

Memory supports continuity and user-controlled dossiers. It is not a raw
transcript archive, surveillance record, hidden personality engine, or source
of automatic truth about another person.

## Use the available memory adapter

Default to session-only operation. A portable Situation Memory Card is a
user-controlled alternative, offered when requested rather than created by default.
Only enable persistence after explicit scope consent and a verified host adapter.
The adapter must demonstrate scoped read/write, inspect, correction, expiry,
export, and deletion with receipts. If a required capability is unavailable or
unverified, keep that case session-only; do not promise unsupported controls.
No raw transcripts or secret person profiles belong in a card.

A skill's memory mode does not control provider chat history, logs, backups, or
training policies. Explain the exact storage scope of a save/delete receipt.
A confirmed application deletion is not proof of erasure from provider logs.
The offline calculator makes no network calls, but that does not make the model
conversation itself local. See the repository's host-capability matrix before
advertising any persistence feature.

The skill must still work without memory, connectors, files, or network access.

## Case modes under the shared host contract

Use one of three modes:

- **OFF:** do not retrieve or write case memory. Honor “memory off,” “do not
  remember this,” and equivalent immediately.
- **CONFIRM_EACH:** propose the exact compact delta and obtain confirmation
  before each write. Use this default only after the user opts into persistence;
  until then the case remains session-only (OFF).
- **AUTO_UPDATE:** is a legacy specialist mode description, not enabled in this consolidated implementation. Use the shared exact-preview/host-attestation contract for every proposed persistent change; a prior broad opt-in cannot bypass it.

Consent is scoped. Enabling memory for one case does not authorize every
relationship or every sensitive detail. The user may narrow the scope, switch
modes, inspect memory, correct it, or revoke it at any time.

## Retrieve before re-interviewing

At the start of a potentially continuing case:

1. retrieve only records whose case or aliases plausibly match the request;
2. say briefly what was remembered and that memory may be stale;
3. verify dates, roles, objectives, boundaries, and other facts that could have
   changed or materially alter the recommendation;
4. use verified memory to avoid asking for the same history again;
5. distinguish current user input from memory-derived context.

Do not force a match. When two cases or people may be confused, ask the user
which one they mean before applying memory.

## Store compact records, profiles, and score snapshots—not conversations

Use a small **Situation Memory Card**:

```text
Memory ID:
Scope and mode:
Last reviewed:
Situation / date window:
Aliases and roles:
Current objective and boundary:
Observed facts and records:
Working actor hypotheses (confidence + falsifier):
Relationship dynamics:
Decision rights, dependencies, and exposure:
Actions tried and observable results:
Current strategy, next review, and stop rule:
Open questions:
Profile version and change note:
Decision Fit Score, coverage, confidence, and flags:
Expiry or update event:
```

Store only what improves a future decision:

- durable user preferences, boundaries, and communication constraints;
- aliases, roles, decision rights, and material dependencies;
- dated facts or records the user identified as reliable;
- repeated interaction tendencies or relationship dynamics stated as bounded,
  revisable hypotheses;
- actions already tried and their observable results;
- active decision, review event, escalation trigger, and stopping rule.
- user-approved profile fields and Decision Fit Score snapshots governed by
  `profiles-and-scoring.md`.

Use a delta update. Do not rewrite the whole history after every message.
Consolidate duplicates and replace stale claims rather than appending forever.

## Keep actor hypotheses bounded

An actor or relationship hypothesis may be retained only when it is
decision-relevant and includes:

- observed basis across more than one ambiguous cue;
- context boundary;
- low, moderate, or high confidence;
- strongest plausible alternative;
- observable falsifier or update condition;
- last-reviewed date.

Example:

> In three deadline situations, A moved decisions into a smaller forum after
> disagreement. Working hypothesis: under time pressure, A centralizes
> coordination. Confidence: moderate. Alternative: the client required a small
> forum. Falsifier: comparable urgent decisions remain consultative.

Do not store assistant-inferred labels such as “A is controlling,” “B is
dishonest,” diagnosis, manipulability, influence rank, vulnerability, pressure
points, or private motive as fact. Attachment, Big Five, MBTI, attraction, or
similar descriptors may be retained only when the user explicitly supplies
them for the named decision, their source is marked, and they are not converted
into diagnosis, compatibility truth, consent, or a prediction about another
person.

## Minimize sensitive information

Prefer aliases and roles. Do not retain:

- raw conversations, screenshots, recordings, or full documents;
- passwords, credentials, contact details, account data, or precise locations;
- unnecessary employer, client, family, or third-party identifiers;
- confidential, privileged, health, biometric, financial, intimate, protected,
  or safeguarding details beyond the minimum explicitly authorized purpose;
- allegations or formal findings beyond the minimum user-confirmed fact needed
  for a safe route;
- covertly collected information or instructions for exploiting another
  person's vulnerabilities.

If a sensitive fact must influence a current safety or formal-route decision,
use it in the conversation but do not automatically promote it into memory.

## Make memory inspectable and correctable

Support these user controls directly:

- **“What do you remember about this?”** Return the relevant card and its
  last-reviewed date.
- **“Correct X to Y.”** Replace the incorrect item and note the correction;
  do not retain the false version as active truth. Recalculate affected score
  dimensions and record whether evidence or weights changed.
- **“Show versions” or “roll back.”** Return the version list or restore the
  selected active snapshot while retaining a visible rollback event.
- **“Export this dossier.”** Return the scoped record in an inspectable format
  without reintroducing excluded raw or sensitive material.
- **“Forget X” or “forget this case.”** Delete the requested item or scoped
  record through the host mechanism and report honestly whether deletion
  succeeded.
- **“Memory off.”** Stop retrieval and writing for the stated scope.
- **“Remember this.”** Show the exact compact delta and use the shared verified
  host-preview protocol. No legacy broad AUTO_UPDATE consent bypasses it.

Never make the user argue with a self-sealing model. New direct evidence,
correction, or deletion overrides an older hypothesis.

## Update at meaningful events

Consider a memory delta when:

- an objective, role, decision right, dependency, or boundary changes;
- a recommended action is taken and an observable result arrives;
- a repeated behavior strengthens or weakens a working hypothesis;
- the route, strategy, reliance level, escalation trigger, or stop rule changes;
- a dossier correction, score dimension, weight, coverage, safety flag, or
  expiry condition materially changes;
- the user explicitly identifies a durable preference or asks to remember it.

Do not update merely because the conversation was long.

## Separate memory from evaluation and publication

Never place real memory content in public fixtures, repositories, issue
trackers, analytics, release artifacts, or model-evaluation packets. A pilot may
record privacy-safe operational metadata, such as whether a write, correction,
or deletion succeeded, but not the personal content.

## Failure handling

If retrieval fails, say so and continue from current context. If writing or
deletion fails, do not claim success; return the intended delta or deletion
target so the user can retain or retry it. Never block urgent safety guidance on
memory access.
