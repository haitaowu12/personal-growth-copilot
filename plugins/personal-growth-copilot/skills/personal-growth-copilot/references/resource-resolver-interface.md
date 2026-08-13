# Current-resource resolver interface

The safety runtime never carries a static crisis-number list. A host adapter is
the only authority allowed to return current contact details.

## Request

The host receives the user-provided jurisdiction, response language, the
`ACUTE_DANGER` urgency class, and a timezone-aware request timestamp. Do not
derive a precise location from unrelated profile data. If the user has not
provided enough location context, return `LOCATION_REQUIRED` without guessing.

## Verified response

Each returned resource must include its name, channel, contact route,
jurisdiction, authoritative HTTPS source, verification time, and expiry time.
The runtime rejects empty, stale, expired, future-verified, or non-HTTPS
records. The host should use the shortest expiry warranted by its source and
re-resolve after expiry or jurisdiction change.

## Failure behavior

Resolver exceptions, empty results, and invalid or stale records become
`UNAVAILABLE`. Do not expose exception text to the model or user. Do not invent
a phone number, service name, availability claim, monitoring capability, or
rescue promise. Continue with the generic immediate route: local emergency or
current crisis services and a trusted person who can be physically present.

Every rendered contact claim must match the exact verified tuple of service
name, contact route, and source URI. A model-authored contact is untrusted.

## Privacy

Transmit only the minimum jurisdiction and language needed. Do not send the
conversation, growth record, diagnosis, identity, or inferred risk narrative
to a resolver. Log only request/result class, timestamps, adapter version, and
opaque audit identifiers; never log user text or contact content.
