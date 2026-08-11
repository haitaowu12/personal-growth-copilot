#!/usr/bin/env python3
"""Protocol fixture only; it is not a target model or behavioral baseline."""

import hashlib
import json
import sys


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


payload = json.load(sys.stdin)
request = payload["request"]
request_sha256 = hashlib.sha256(canonical(payload)).hexdigest()
response_id = hashlib.sha256(
    canonical(
        {
            "case": request["case_id"],
            "system": request["system_id"],
            "variant": request["variant_id"],
            "repetition": request["repetition"],
            "turn": request["turn_id"],
            "history_length": len(request["history"]),
        }
    )
).hexdigest()[:24]
json.dump(
    {
        "protocol": "pgc-stdio-v1",
        "request_sha256": request_sha256,
        "provider_identity_sha256": payload["provider_identity_sha256"],
        "text": f"Protocol fixture response {response_id}.",
        "memory_write_attempted": False,
        "resource_claims": [],
        "provider_response_id": "fixture-" + response_id,
    },
    sys.stdout,
    ensure_ascii=False,
)
