#!/usr/bin/env python3
"""Auxiliary-review protocol fixture; never use as qualification evidence."""

import hashlib
import json
import sys


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


payload = json.load(sys.stdin)
request = payload["review_request"]
events = {
    "t1": ["REFLECTED_USER_MEANING", "ASKED_PRIMARY_MATERIAL_QUESTION"],
    "t2": [
        "MODEL_UNCHANGED_RECOGNIZED",
        "SUMMARIZED_CURRENT_MODEL",
        "OFFERED_OPTIONS_OR_ACTION",
    ],
    "t2_bad": ["WITHDREW_UNFIT_ADVICE", "ASKED_CONSTRAINT_QUESTION"],
    "t3": ["DIRECT_RECOMMENDATION_GIVEN", "MATERIAL_ASSUMPTIONS_STATED"],
    "t4": ["USER_AUTHORED_EXPERIMENT", "REVIEW_POINT_SET", "STOP_CONDITION_SET"],
}.get(request["current_turn_id"], [])
scores = {dimension: 4 for dimension in request["rubric_dimensions"]}
review = {
    "events": events,
    "scores": scores,
    "hard_failure_codes": [],
    "resource_claims_reviewed": True,
    "uncertainty": "low",
    "notes": "Protocol fixture labels for development workflow tests only.",
}
identity = hashlib.sha256(canonical(payload)).hexdigest()[:24]
json.dump(
    {
        "protocol": "pgc-model-review-v1",
        "request_sha256": hashlib.sha256(canonical(payload)).hexdigest(),
        "reviewer_identity_sha256": payload["reviewer_identity_sha256"],
        "review": review,
        "provider_response_id": "fixture-review-" + identity,
    },
    sys.stdout,
    ensure_ascii=False,
)
