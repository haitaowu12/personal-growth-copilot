#!/usr/bin/env python3
"""Stateful Ed25519 witness used only by attempt-inventory tests."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def main() -> int:
    event = json.load(__import__("sys").stdin)
    state_path = Path(os.environ["PGC_TEST_WITNESS_STATE"])
    private_key = Path(os.environ["PGC_TEST_WITNESS_PRIVATE_KEY"])
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = {"campaign_id": event["campaign_id"], "count": 0, "head": None}
    if (
        state["campaign_id"] != event["campaign_id"]
        or event["sequence"] != state["count"]
        or event["previous_event_sha256"] != state["head"]
    ):
        return 2
    payload = {
        "domain": "pgc-attempt-witness-receipt-v1",
        "campaign_id": event["campaign_id"],
        "candidate_commit": event["candidate_commit"],
        "event_sha256": event["event_sha256"],
        "sequence": event["sequence"],
        "previous_event_sha256": event["previous_event_sha256"],
        "witnessed_at": event["occurred_at"],
        "nonce": "witness-nonce-" + event["event_sha256"][:32],
    }
    with tempfile.TemporaryDirectory(prefix="pgc-witness-fixture-") as directory_name:
        directory = Path(directory_name)
        payload_path = directory / "payload.json"
        signature_path = directory / "signature.bin"
        payload_path.write_bytes(canonical_bytes(payload))
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private_key),
                "-rawin",
                "-in",
                str(payload_path),
                "-out",
                str(signature_path),
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return 3
        signature = base64.b64encode(signature_path.read_bytes()).decode("ascii")
    next_state = {
        "campaign_id": event["campaign_id"],
        "count": event["sequence"] + 1,
        "head": event["event_sha256"],
    }
    temporary_state = state_path.with_suffix(".new")
    temporary_state.write_text(
        json.dumps(next_state, sort_keys=True), encoding="utf-8"
    )
    os.replace(temporary_state, state_path)
    print(
        json.dumps(
            {
                "schema_version": "1.0",
                "key_id": "attempt-witness",
                "payload": payload,
                "signature_base64": signature,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
