# Session Capsule

Use when the user wants a compact take-away or asks to save the session. A
capsule is a user-readable summary and optional persistence preview. It is not
automatic memory, a raw transcript, a hidden dossier, or proof that a host
wrote anything.

## Build the capsule

Preserve only decision-useful content:

- session objective;
- one short user-approved wording fragment;
- confirmed facts with source tags;
- tentative hypotheses and alternatives;
- unknowns that could change direction;
- user-chosen action, intentional non-action, or unresolved state;
- prediction and disconfirming observation;
- review point and open question;
- exact proposed memory delta;
- persistence status.

Use `assets/session-capsule.schema.json`. Keep wording compact. Do not include
raw journals, full conversations, trauma narratives, credentials, third-party
profiles, or unnecessary identifiers.

## Persistence states

- `not_requested`: no delta and no host receipt.
- `previewed`: exact delta shown; no host receipt; no write claim.
- `confirmed_by_host`: exact delta plus host receipt hash after the host reports
  a successful write.

User approval in conversation does not equal host confirmation. Never mark
`confirmed_by_host` from model-authored text. If the host is unavailable,
return a `previewed` capsule the user may copy or discard.

## Review use

At the review point, compare observation with prediction and disconfirming
observation. Retain, narrow, supersede, or reject the hypothesis. Record
non-attempt and intentional non-action distinctly. A capsule proves only what
it contains and what the host receipt attests; it does not establish benefit.
