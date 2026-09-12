"""Governed evaluation-system identities and profile bindings."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "evals/system-contract.json"
CONTRACT_SCHEMA_PATH = ROOT / "evals/system-contract.schema.json"
EXPECTED_SYSTEM_CONTRACT = (
    (
        "target",
        "product",
        "READ_ONLY_USER_APPROVED",
        "HOST_EXPLICIT_ONLY",
    ),
    (
        "direct_assistant",
        "matched_direct_baseline",
        "CONVERSATION_ONLY",
        "DISABLED",
    ),
    (
        "structured_reflection",
        "matched_noncoaching_baseline",
        "CONVERSATION_ONLY",
        "DISABLED",
    ),
    (
        "strong_generalist",
        "same_capability_generalist_comparator",
        "READ_ONLY_USER_APPROVED",
        "DISABLED",
    ),
    (
        "minimal_visible_model",
        "minimal_visible_model_comparator",
        "READ_ONLY_USER_APPROVED",
        "DISABLED",
    ),
)


class SystemContractError(ValueError):
    """Raised when the committed system contract is malformed or unsafe."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repository_file(relative_path: str) -> Path:
    candidate = ROOT / relative_path
    if candidate.is_symlink():
        raise SystemContractError(f"system profile path may not be a symlink: {relative_path}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(ROOT.resolve())
    except (OSError, ValueError) as exc:
        raise SystemContractError(
            f"system profile path is unavailable or escapes the repository: {relative_path}"
        ) from exc
    if not resolved.is_file():
        raise SystemContractError(f"system profile path is not a file: {relative_path}")
    return resolved


def load_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    schema = json.loads(CONTRACT_SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_errors = sorted(
        Draft202012Validator(schema).iter_errors(contract),
        key=lambda item: list(item.absolute_path),
    )
    if schema_errors:
        first = schema_errors[0]
        path = ".".join(str(part) for part in first.absolute_path) or "$"
        raise SystemContractError(f"invalid system contract at {path}: {first.message}")
    observed_contract = tuple(
        (
            system["id"],
            system["role"],
            system["context_policy"],
            system["memory_write_policy"],
        )
        for system in contract["systems"]
    )
    if observed_contract != EXPECTED_SYSTEM_CONTRACT:
        raise SystemContractError(
            "system contract identities, order, roles, and policies must match the governed contract"
        )
    for system in contract["systems"]:
        if system["profile_path"] not in system["bundle_paths"]:
            raise SystemContractError(
                f"{system['id']} profile_path must appear in bundle_paths"
            )
        for relative_path in system["bundle_paths"]:
            _repository_file(relative_path)
    return contract


def system_ids(contract: dict[str, Any] | None = None) -> tuple[str, ...]:
    current = contract or load_contract()
    return tuple(system["id"] for system in current["systems"])


def system_by_id(contract: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    current = contract or load_contract()
    return {system["id"]: system for system in current["systems"]}


def contract_sha256(contract: dict[str, Any] | None = None) -> str:
    return digest(contract or load_contract())


def profile_sha256(contract: dict[str, Any] | None = None) -> dict[str, str]:
    current = contract or load_contract()
    return {
        system["id"]: file_sha256(_repository_file(system["profile_path"]))
        for system in current["systems"]
    }


def profile_bundle_sha256(
    contract: dict[str, Any] | None = None,
) -> dict[str, str]:
    current = contract or load_contract()
    return {
        system["id"]: digest(
            [
                {
                    "path": relative_path,
                    "sha256": file_sha256(_repository_file(relative_path)),
                }
                for relative_path in system["bundle_paths"]
            ]
        )
        for system in current["systems"]
    }


SYSTEM_CONTRACT = load_contract()
SYSTEM_IDS = system_ids(SYSTEM_CONTRACT)
SYSTEMS_BY_ID = system_by_id(SYSTEM_CONTRACT)
NON_TARGET_PROFILE_PATHS = {
    system_id: _repository_file(system["profile_path"])
    for system_id, system in SYSTEMS_BY_ID.items()
    if system_id != "target"
}
WRITE_DISABLED_SYSTEMS = {
    system_id
    for system_id, system in SYSTEMS_BY_ID.items()
    if system["memory_write_policy"] == "DISABLED"
}
