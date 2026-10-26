#!/usr/bin/env python3
"""Build hash-complete external evidence sources without inventing observations.

Every command is create-only.  Inputs containing identity, independence,
calibration, access, consent, episode, finding, or incident facts must come from
the responsible external role.  The builder derives hashes, exact result
coverage, event chains, and witness payloads; it never creates a signature or a
passing observation.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "evals"))

import campaign  # noqa: E402
import release_evidence  # noqa: E402
import target_session  # noqa: E402

WITNESS_REQUEST_SCHEMA = ROOT / "release/external-witness-request.schema.json"


class SourceBuilderError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return release_evidence.canonical_bytes(value)


def digest(value: object) -> str:
    return release_evidence.digest(value)


def object_hash(value: dict[str, Any], field: str) -> str:
    return release_evidence.object_hash(value, field)


def timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SourceBuilderError("builder clock must be timezone aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def now() -> datetime:
    return datetime.now(timezone.utc)


def source_identity() -> str:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty:
        raise SourceBuilderError("external source construction requires a clean tree")
    return commit


def read_bytes(path: Path, maximum: int = 50 * 1024 * 1024) -> bytes:
    return release_evidence.read_once(path, maximum=maximum)


def load_object(path: Path, label: str) -> dict[str, Any]:
    return release_evidence.json_object(read_bytes(path), label)


def file_hash(path: Path) -> str:
    return hashlib.sha256(read_bytes(path)).hexdigest()


def relative_path(path: Path, root: Path) -> str:
    if path.is_symlink():
        raise SourceBuilderError("evidence path may not be a symlink")
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise SourceBuilderError("evidence input must remain inside the packet root") from exc
    return relative.as_posix()


def schema_errors(value: object, schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(value),
            key=lambda item: list(item.absolute_path),
        )
    ]


def external_source_errors(value: object) -> list[str]:
    return release_evidence.schema_errors(value, "external_source")


def write_private_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(canonical_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def reviewer_source(
    *,
    output: Path,
    config_path: Path,
    manifest_path: Path,
    calibration_set_path: Path,
    declarations_path: Path,
    completed_at: datetime,
    clock: Callable[[], datetime] = now,
) -> dict[str, Any]:
    root = output.parent.resolve()
    config = load_object(config_path, "target config")
    suite = load_object(ROOT / "evals/cases.json", "canonical suite")
    if errors := target_session.validate_target_config(config, suite):
        raise SourceBuilderError("invalid target config: " + "; ".join(errors))
    manifest = load_object(manifest_path, "result manifest")
    results = campaign.load_manifest_results(
        manifest=manifest,
        manifest_path=manifest_path,
        suite=suite,
        config=config,
        clock=clock,
    )
    declarations = load_object(declarations_path, "reviewer declarations")
    if set(declarations) != {"reviewers"} or not isinstance(
        declarations["reviewers"], list
    ):
        raise SourceBuilderError("reviewer declarations must contain only a reviewers array")
    use_count: dict[str, int] = {}
    for result in results:
        for review in result["reviews"]:
            for reviewer in review["reviewers"]:
                reviewer_id = reviewer["reviewer_id"]
                use_count[reviewer_id] = use_count.get(reviewer_id, 0) + 1
    declared_ids = [item.get("reviewer_id") for item in declarations["reviewers"]]
    if len(declared_ids) != len(set(declared_ids)) or set(declared_ids) != set(use_count):
        raise SourceBuilderError("reviewer declarations do not cover the exact used reviewer set")
    reviewer_evidence = []
    for item in declarations["reviewers"]:
        expected = {
            "reviewer_id",
            "languages",
            "identity_evidence_path",
            "independence_evidence_path",
            "calibration_evidence_path",
            "calibrated_at",
            "identity_verified",
            "independence_verified",
            "calibration_passed",
        }
        if set(item) != expected:
            raise SourceBuilderError("reviewer declaration fields do not match the builder contract")
        identity_path = release_evidence.safe_path(root, item["identity_evidence_path"])
        identity = load_object(identity_path, "reviewer identity attestation")
        if errors := release_evidence.schema_errors(identity, "reviewer_identity"):
            raise SourceBuilderError("invalid reviewer identity attestation: " + "; ".join(errors))
        if identity["reviewer_id"] != item["reviewer_id"]:
            raise SourceBuilderError("reviewer identity attestation binds another reviewer")
        independence_path = release_evidence.safe_path(
            root, item["independence_evidence_path"]
        )
        calibration_path = release_evidence.safe_path(
            root, item["calibration_evidence_path"]
        )
        reviewer_evidence.append(
            {
                "reviewer_id": item["reviewer_id"],
                "subject_sha256": identity["subject_sha256"],
                "languages": item["languages"],
                "identity_evidence_path": item["identity_evidence_path"],
                "identity_evidence_sha256": file_hash(identity_path),
                "independence_evidence_path": item["independence_evidence_path"],
                "independence_evidence_sha256": file_hash(independence_path),
                "calibration_evidence_path": item["calibration_evidence_path"],
                "calibration_evidence_sha256": file_hash(calibration_path),
                "calibrated_at": item["calibrated_at"],
                "identity_verified": item["identity_verified"],
                "independence_verified": item["independence_verified"],
                "calibration_passed": item["calibration_passed"],
                "used_run_count": use_count[item["reviewer_id"]],
            }
        )
    source = {
        "schema_version": "1.0",
        "evidence_class": "reviewer-attestation-source",
        "candidate_commit": config["source_commit"],
        "completed_at": timestamp(completed_at),
        "rubric_sha256": config["review"]["rubric_sha256"],
        "calibration_set_path": relative_path(calibration_set_path, root),
        "calibration_set_sha256": file_hash(calibration_set_path),
        "config_path": relative_path(config_path, root),
        "config_sha256": file_hash(config_path),
        "result_manifest_path": relative_path(manifest_path, root),
        "result_manifest_sha256": file_hash(manifest_path),
        "reviewers": reviewer_evidence,
    }
    if errors := external_source_errors(source):
        raise SourceBuilderError("reviewer source schema failure: " + "; ".join(errors))
    return source


def bilingual_source(
    *,
    output: Path,
    reviewer_source_path: Path,
    fluent_reviewer_ids: list[str],
    completed_at: datetime,
    clock: Callable[[], datetime] = now,
) -> dict[str, Any]:
    root = output.parent.resolve()
    reviewer_source = load_object(reviewer_source_path, "reviewer source")
    reviewer_root = reviewer_source_path.parent.resolve()
    config_path = release_evidence.safe_path(
        reviewer_root, reviewer_source["config_path"]
    )
    manifest_path = release_evidence.safe_path(
        reviewer_root, reviewer_source["result_manifest_path"]
    )
    config = load_object(config_path, "target config")
    manifest = load_object(manifest_path, "result manifest")
    suite = load_object(ROOT / "evals/cases.json", "canonical suite")
    results = campaign.load_manifest_results(
        manifest=manifest,
        manifest_path=manifest_path,
        suite=suite,
        config=config,
        clock=clock,
    )
    language_by_case = {item["id"]: item["language"] for item in suite["cases"]}
    reviews = []
    for entry, result in zip(manifest["results"], results, strict=True):
        language = language_by_case[result["run"]["case_id"]]
        if language not in {"zh", "mixed"}:
            continue
        for review in result["reviews"]:
            primary = {
                item["role"]: item
                for item in review["reviewers"]
                if item["role"] in {"primary_1", "primary_2"}
            }
            if set(primary) != {"primary_1", "primary_2"}:
                raise SourceBuilderError("bilingual result lacks both primary reviewers")
            failure_codes = sorted(
                code
                for code in (
                    list(review["adjudication"]["events"])
                    + list(review["adjudication"]["hard_failure_codes"])
                )
                if any(marker in code for marker in campaign.CHINESE_FAILURE_MARKERS)
            )
            reviews.append(
                {
                    "review_id": review["review_sha256"],
                    "run_id": result["run"]["run_id"],
                    "system_id": result["run"]["system_id"],
                    "language": language,
                    "result_sha256": entry["sha256"],
                    "primary_1_reviewer_id": primary["primary_1"]["reviewer_id"],
                    "primary_2_reviewer_id": primary["primary_2"]["reviewer_id"],
                    "primary_1_scores": primary["primary_1"]["scores"],
                    "primary_2_scores": primary["primary_2"]["scores"],
                    "meaning_or_safety_failure_codes": failure_codes,
                }
            )
    if not reviews:
        raise SourceBuilderError("no Chinese or mixed-language reviews were found")
    source = {
        "schema_version": "1.0",
        "evidence_class": "bilingual-review-source",
        "candidate_commit": config["source_commit"],
        "completed_at": timestamp(completed_at),
        "reviewer_source_path": relative_path(reviewer_source_path, root),
        "reviewer_source_sha256": file_hash(reviewer_source_path),
        "fluent_reviewer_ids": sorted(set(fluent_reviewer_ids)),
        "expected_review_ids": sorted(item["review_id"] for item in reviews),
        "reviews": sorted(reviews, key=lambda item: item["review_id"]),
    }
    if errors := external_source_errors(source):
        raise SourceBuilderError("bilingual source schema failure: " + "; ".join(errors))
    return source


def holdout_seal(
    *,
    output: Path,
    candidate_commit: str,
    sealed_at: datetime,
    public_case_count: int,
    sealed_case_ids: list[str],
    ciphertext_path: Path,
    case_schema_path: Path,
    witness_public_key_path: Path,
    authors_path: Path,
) -> dict[str, Any]:
    root = output.parent.resolve()
    declarations = load_object(authors_path, "holdout author declarations")
    if set(declarations) != {"authors"} or not isinstance(declarations["authors"], list):
        raise SourceBuilderError("holdout author declarations must contain only authors")
    authors = []
    for item in declarations["authors"]:
        expected = {
            "author_id",
            "subject_sha256",
            "identity_evidence_path",
            "independence_evidence_path",
            "authorship_evidence_path",
            "independence_verified",
        }
        if set(item) != expected:
            raise SourceBuilderError("holdout author declaration fields mismatch")
        author = deepcopy(item)
        for prefix in ("identity", "independence", "authorship"):
            path = release_evidence.safe_path(root, item[f"{prefix}_evidence_path"])
            author[f"{prefix}_evidence_sha256"] = file_hash(path)
        authors.append(author)
    seal = {
        "schema_version": "1.0",
        "evidence_class": "holdout-seal",
        "candidate_commit": candidate_commit,
        "sealed_at": timestamp(sealed_at),
        "public_case_count": public_case_count,
        "sealed_case_ids": sealed_case_ids,
        "ciphertext_path": relative_path(ciphertext_path, root),
        "ciphertext_sha256": file_hash(ciphertext_path),
        "case_schema_path": relative_path(case_schema_path, root),
        "case_schema_sha256": file_hash(case_schema_path),
        "witness_public_key_path": relative_path(witness_public_key_path, root),
        "witness_public_key_sha256": file_hash(witness_public_key_path),
        "authors": authors,
    }
    seal["seal_sha256"] = object_hash(seal, "seal_sha256")
    if errors := release_evidence.schema_errors(seal, "holdout_seal"):
        raise SourceBuilderError("holdout seal schema failure: " + "; ".join(errors))
    return seal


def holdout_access_audit(
    *,
    output: Path,
    candidate_commit: str,
    seal_path: Path,
    events_path: Path,
    generated_at: datetime,
) -> dict[str, Any]:
    root = output.parent.resolve()
    seal = load_object(seal_path, "holdout seal")
    declarations = load_object(events_path, "holdout access declarations")
    if set(declarations) != {"events"} or not isinstance(declarations["events"], list):
        raise SourceBuilderError("access declarations must contain only events")
    events = []
    for item in declarations["events"]:
        expected = {"event_id", "actor_role", "accessed_at", "evidence_path"}
        if set(item) != expected:
            raise SourceBuilderError("access declaration fields mismatch")
        evidence = release_evidence.safe_path(root, item["evidence_path"])
        events.append({**item, "evidence_sha256": file_hash(evidence)})
    audit = {
        "schema_version": "1.0",
        "evidence_class": "holdout-access-audit",
        "candidate_commit": candidate_commit,
        "holdout_seal_sha256": seal["seal_sha256"],
        "generated_at": timestamp(generated_at),
        "events": events,
    }
    audit["audit_sha256"] = object_hash(audit, "audit_sha256")
    if errors := release_evidence.schema_errors(audit, "holdout_access"):
        raise SourceBuilderError("holdout access schema failure: " + "; ".join(errors))
    return audit


def holdout_result(
    *,
    output: Path,
    candidate_commit: str,
    case_id: str,
    completed_at: datetime,
    automated_status: str,
    hard_failure_codes: list[str],
    transcript_path: Path,
) -> dict[str, Any]:
    root = output.parent.resolve()
    result = {
        "schema_version": "1.0",
        "evidence_class": "holdout-case-result",
        "candidate_commit": candidate_commit,
        "case_id": case_id,
        "completed_at": timestamp(completed_at),
        "automated_status": automated_status,
        "hard_failure_codes": sorted(set(hard_failure_codes)),
        "transcript_path": relative_path(transcript_path, output.parent.resolve()),
        "transcript_sha256": file_hash(transcript_path),
    }
    result["result_sha256"] = object_hash(result, "result_sha256")
    if errors := release_evidence.schema_errors(result, "holdout_result"):
        raise SourceBuilderError("holdout result schema failure: " + "; ".join(errors))
    return result


def witness_request(
    *,
    kind: str,
    candidate_commit: str,
    public_key_path: Path,
    root: Path,
    payload: dict[str, Any],
    unsigned_artifact: dict[str, Any],
) -> dict[str, Any]:
    request = {
        "schema_version": "1.0",
        "evidence_class": "external-witness-signing-request",
        "kind": kind,
        "candidate_commit": candidate_commit,
        "public_key_path": relative_path(public_key_path, root),
        "public_key_sha256": file_hash(public_key_path),
        "payload": payload,
        "unsigned_artifact": unsigned_artifact,
    }
    request["request_sha256"] = object_hash(request, "request_sha256")
    if errors := schema_errors(request, WITNESS_REQUEST_SCHEMA):
        raise SourceBuilderError("witness request schema failure: " + "; ".join(errors))
    return request


def prepare_holdout_attempt(
    *,
    output: Path,
    candidate_commit: str,
    case_id: str,
    result_path: Path,
    events_path: Path,
    seal_path: Path,
    issued_at: datetime,
    nonce: str,
) -> dict[str, Any]:
    root = output.parent.resolve()
    result = load_object(result_path, "holdout result")
    seal = load_object(seal_path, "holdout seal")
    declarations = load_object(events_path, "holdout attempt declarations")
    if set(declarations) != {"events"} or not isinstance(declarations["events"], list):
        raise SourceBuilderError("holdout attempt declarations must contain only events")
    events = []
    previous = None
    for sequence, item in enumerate(declarations["events"]):
        expected = {"attempt_id", "occurred_at", "outcome"}
        if set(item) != expected:
            raise SourceBuilderError("holdout attempt declaration fields mismatch")
        event = {
            "sequence": sequence,
            "previous_event_sha256": previous,
            "attempt_id": item["attempt_id"],
            "occurred_at": item["occurred_at"],
            "outcome": item["outcome"],
            "result_sha256": result["result_sha256"] if item["outcome"] == "PASS" else None,
        }
        event["event_sha256"] = object_hash(event, "event_sha256")
        previous = event["event_sha256"]
        events.append(event)
    if not events:
        raise SourceBuilderError("holdout attempt inventory requires at least one event")
    unsigned = {
        "schema_version": "1.0",
        "evidence_class": "holdout-attempt-inventory",
        "candidate_commit": candidate_commit,
        "case_id": case_id,
        "events": events,
    }
    ledger_hash = release_evidence.selected_hash(
        unsigned,
        ("schema_version", "evidence_class", "candidate_commit", "case_id", "events"),
    )
    unsigned["ledger_sha256"] = ledger_hash
    payload = {
        "domain": "pgc-holdout-attempt-witness-v1",
        "candidate_commit": candidate_commit,
        "case_id": case_id,
        "ledger_sha256": ledger_hash,
        "event_count": len(events),
        "head_event_sha256": events[-1]["event_sha256"],
        "issued_at": timestamp(issued_at),
        "nonce": nonce,
    }
    key_path = release_evidence.safe_path(
        seal_path.parent.resolve(), seal["witness_public_key_path"]
    )
    return witness_request(
        kind="holdout_attempt",
        candidate_commit=candidate_commit,
        public_key_path=key_path,
        root=root,
        payload=payload,
        unsigned_artifact=unsigned,
    )


def _load_signature(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    try:
        base64.b64decode(value, validate=True)
    except Exception as exc:
        raise SourceBuilderError("signature file is not canonical base64") from exc
    return value


def assemble_holdout_attempt(
    *, output: Path, request_path: Path, signature_path: Path
) -> dict[str, Any]:
    request = load_object(request_path, "holdout witness request")
    if request.get("kind") != "holdout_attempt" or request.get(
        "request_sha256"
    ) != object_hash(request, "request_sha256"):
        raise SourceBuilderError("holdout witness request is invalid")
    signature = _load_signature(signature_path)
    key = release_evidence.load_bound_public_key(
        request_path.parent.resolve(),
        request["public_key_path"],
        request["public_key_sha256"],
        "holdout witness",
    )
    release_evidence.verify_signature(request["payload"], signature, key)
    attempt = {
        **deepcopy(request["unsigned_artifact"]),
        "witness_receipt": {
            "payload": deepcopy(request["payload"]),
            "signature_base64": signature,
        },
    }
    attempt["attempt_sha256"] = object_hash(attempt, "attempt_sha256")
    if errors := release_evidence.schema_errors(attempt, "holdout_attempt"):
        raise SourceBuilderError("holdout attempt schema failure: " + "; ".join(errors))
    return attempt


def holdout_source(
    *,
    output: Path,
    candidate_commit: str,
    seal_path: Path,
    access_audit_path: Path,
    result_paths: list[Path],
    attempt_paths: list[Path],
    revealed_at: datetime,
    completed_at: datetime,
) -> dict[str, Any]:
    if len(result_paths) != len(attempt_paths):
        raise SourceBuilderError("holdout result and attempt counts differ")
    root = output.parent.resolve()
    seal = load_object(seal_path, "holdout seal")
    audit = load_object(access_audit_path, "holdout access audit")
    attempts_by_case = {
        load_object(path, "holdout attempt")["case_id"]: path
        for path in attempt_paths
    }
    references = []
    for result_path in result_paths:
        result = load_object(result_path, "holdout result")
        attempt_path = attempts_by_case.get(result["case_id"])
        if attempt_path is None:
            raise SourceBuilderError("holdout result has no matching attempt inventory")
        attempt = load_object(attempt_path, "holdout attempt")
        references.append(
            {
                "case_id": result["case_id"],
                "result_path": relative_path(result_path, root),
                "result_file_sha256": file_hash(result_path),
                "result_sha256": result["result_sha256"],
                "attempt_inventory_path": relative_path(attempt_path, root),
                "attempt_inventory_file_sha256": file_hash(attempt_path),
                "attempt_inventory_sha256": attempt["attempt_sha256"],
            }
        )
    source = {
        "schema_version": "1.0",
        "evidence_class": "holdout-source",
        "candidate_commit": candidate_commit,
        "seal_path": relative_path(seal_path, root),
        "seal_file_sha256": file_hash(seal_path),
        "seal_sha256": seal["seal_sha256"],
        "revealed_at": timestamp(revealed_at),
        "completed_at": timestamp(completed_at),
        "access_audit_path": relative_path(access_audit_path, root),
        "access_audit_file_sha256": file_hash(access_audit_path),
        "access_audit_sha256": audit["audit_sha256"],
        "results": sorted(references, key=lambda item: item["case_id"]),
    }
    if errors := external_source_errors(source):
        raise SourceBuilderError("holdout source schema failure: " + "; ".join(errors))
    return source


def privacy_host_identity(
    *,
    output: Path,
    named_host: str,
    environment_id: str,
    storage_root: Path,
    audit_id: str,
    audit_public_key_path: Path,
    captured_at: datetime,
) -> dict[str, Any]:
    root = output.parent.resolve()
    identity = {
        "schema_version": "1.0",
        "evidence_class": "privacy-host-identity",
        "named_host": named_host,
        "environment_id": environment_id,
        "storage_root_sha256": release_evidence.filesystem_object_identity(
            storage_root
        ),
        "audit_id": audit_id,
        "audit_public_key_path": relative_path(audit_public_key_path, root),
        "audit_public_key_sha256": file_hash(audit_public_key_path),
        "captured_at": timestamp(captured_at),
    }
    if errors := release_evidence.schema_errors(identity, "privacy_host"):
        raise SourceBuilderError(
            "privacy host-identity schema failure: " + "; ".join(errors)
        )
    return identity


def prepare_privacy_source(
    *,
    output: Path,
    candidate_commit: str,
    host_identity_path: Path,
    checks_path: Path,
    findings_path: Path,
    retention_days: int,
    completed_at: datetime,
    nonce: str,
) -> dict[str, Any]:
    root = output.parent.resolve()
    host_identity = load_object(host_identity_path, "privacy host identity")
    if errors := release_evidence.schema_errors(host_identity, "privacy_host"):
        raise SourceBuilderError("invalid privacy host identity: " + "; ".join(errors))
    check_declarations = load_object(checks_path, "privacy check declarations")
    finding_declarations = load_object(findings_path, "privacy finding declarations")
    if set(check_declarations) != {"checks"} or not isinstance(
        check_declarations["checks"], list
    ):
        raise SourceBuilderError("privacy check declarations must contain only checks")
    if set(finding_declarations) != {"findings"} or not isinstance(
        finding_declarations["findings"], list
    ):
        raise SourceBuilderError(
            "privacy finding declarations must contain only findings"
        )
    checks = []
    for item in check_declarations["checks"]:
        expected = {"check_id", "status", "executed_at", "evidence_path"}
        if set(item) != expected:
            raise SourceBuilderError("privacy check declaration fields mismatch")
        evidence = release_evidence.safe_path(root, item["evidence_path"])
        checks.append({**item, "evidence_sha256": file_hash(evidence)})
    findings = []
    for item in finding_declarations["findings"]:
        expected = {"finding_id", "severity", "status", "evidence_path"}
        if set(item) != expected:
            raise SourceBuilderError("privacy finding declaration fields mismatch")
        evidence = release_evidence.safe_path(root, item["evidence_path"])
        findings.append({**item, "evidence_sha256": file_hash(evidence)})
    unsigned = {
        "schema_version": "1.0",
        "evidence_class": "privacy-preflight-source",
        "candidate_commit": candidate_commit,
        "named_host": host_identity["named_host"],
        "host_identity_path": relative_path(host_identity_path, root),
        "host_identity_sha256": file_hash(host_identity_path),
        "completed_at": timestamp(completed_at),
        "retention_days": retention_days,
        "checks": checks,
        "findings": findings,
    }
    unsigned["audit_sha256"] = release_evidence.selected_hash(
        unsigned,
        (
            "candidate_commit",
            "named_host",
            "host_identity_sha256",
            "completed_at",
            "retention_days",
            "checks",
            "findings",
        ),
    )
    unsigned["audit_event_count"] = len(checks) + len(findings)
    payload = {
        "domain": "pgc-privacy-audit-witness-v1",
        "candidate_commit": candidate_commit,
        "audit_id": host_identity["audit_id"],
        "host_identity_sha256": unsigned["host_identity_sha256"],
        "audit_sha256": unsigned["audit_sha256"],
        "event_count": unsigned["audit_event_count"],
        "completed_at": unsigned["completed_at"],
        "nonce": nonce,
    }
    key_path = release_evidence.safe_path(
        host_identity_path.parent.resolve(), host_identity["audit_public_key_path"]
    )
    return witness_request(
        kind="privacy_audit",
        candidate_commit=candidate_commit,
        public_key_path=key_path,
        root=root,
        payload=payload,
        unsigned_artifact=unsigned,
    )


def assemble_privacy_source(
    *, output: Path, request_path: Path, signature_path: Path
) -> dict[str, Any]:
    request = load_object(request_path, "privacy witness request")
    if request.get("kind") != "privacy_audit" or request.get(
        "request_sha256"
    ) != object_hash(request, "request_sha256"):
        raise SourceBuilderError("privacy witness request is invalid")
    signature = _load_signature(signature_path)
    key = release_evidence.load_bound_public_key(
        request_path.parent.resolve(),
        request["public_key_path"],
        request["public_key_sha256"],
        "privacy audit",
    )
    release_evidence.verify_signature(request["payload"], signature, key)
    source = {
        **deepcopy(request["unsigned_artifact"]),
        "audit_receipt": {
            "payload": deepcopy(request["payload"]),
            "signature_base64": signature,
        },
    }
    if errors := external_source_errors(source):
        raise SourceBuilderError("privacy source schema failure: " + "; ".join(errors))
    return source


def pilot_protocol(
    *,
    output: Path,
    candidate_commit: str,
    preregistered_at: datetime,
    ledger_id: str,
    witness_public_key_path: Path,
    planned_episode_ids: list[str],
) -> dict[str, Any]:
    root = output.parent.resolve()
    protocol = {
        "schema_version": "1.0",
        "evidence_class": "pilot-protocol",
        "candidate_commit": candidate_commit,
        "preregistered_at": timestamp(preregistered_at),
        "ledger_id": ledger_id,
        "witness_public_key_path": relative_path(witness_public_key_path, root),
        "witness_public_key_sha256": file_hash(witness_public_key_path),
        "planned_episode_ids": planned_episode_ids,
        "minimum_duration_days": 28,
        "maximum_duration_days": 56,
        "stop_categories": [
            "privacy",
            "hard_safety",
            "dependence",
            "fabricated_persistence",
        ],
    }
    if errors := release_evidence.schema_errors(protocol, "pilot_protocol"):
        raise SourceBuilderError("pilot protocol schema failure: " + "; ".join(errors))
    return protocol


def prepare_pilot_source(
    *,
    output: Path,
    candidate_commit: str,
    protocol_path: Path,
    episodes_path: Path,
    incidents_path: Path,
    started_at: datetime,
    ended_at: datetime,
    nonce: str,
) -> dict[str, Any]:
    root = output.parent.resolve()
    protocol = load_object(protocol_path, "pilot protocol")
    if errors := release_evidence.schema_errors(protocol, "pilot_protocol"):
        raise SourceBuilderError("invalid pilot protocol: " + "; ".join(errors))
    episode_declarations = load_object(episodes_path, "pilot episode declarations")
    incident_declarations = load_object(incidents_path, "pilot incident declarations")
    if set(episode_declarations) != {"episodes"} or not isinstance(
        episode_declarations["episodes"], list
    ):
        raise SourceBuilderError("pilot episode declarations must contain only episodes")
    if set(incident_declarations) != {"incidents"} or not isinstance(
        incident_declarations["incidents"], list
    ):
        raise SourceBuilderError(
            "pilot incident declarations must contain only incidents"
        )
    episodes = []
    for item in episode_declarations["episodes"]:
        expected = {
            "episode_id",
            "scheduled_at",
            "closed_at",
            "outcome",
            "consent_evidence_path",
            "episode_evidence_path",
            "withdrawal_requested_at",
            "withdrawal_honored_at",
            "deletion_requested",
            "deletion_completed_at",
        }
        if set(item) != expected:
            raise SourceBuilderError("pilot episode declaration fields mismatch")
        consent_path = release_evidence.safe_path(
            root, item["consent_evidence_path"]
        )
        episode_path = release_evidence.safe_path(
            root, item["episode_evidence_path"]
        )
        episodes.append(
            {
                **item,
                "consent_evidence_sha256": file_hash(consent_path),
                "episode_evidence_sha256": file_hash(episode_path),
            }
        )
    incidents = []
    for item in incident_declarations["incidents"]:
        expected = {
            "incident_id",
            "category",
            "severity",
            "detected_at",
            "evidence_path",
        }
        if set(item) != expected:
            raise SourceBuilderError("pilot incident declaration fields mismatch")
        evidence_path = release_evidence.safe_path(root, item["evidence_path"])
        incidents.append({**item, "evidence_sha256": file_hash(evidence_path)})
    unsigned = {
        "schema_version": "1.0",
        "evidence_class": "pilot-source",
        "candidate_commit": candidate_commit,
        "protocol_path": relative_path(protocol_path, root),
        "protocol_sha256": file_hash(protocol_path),
        "preregistered_at": protocol["preregistered_at"],
        "started_at": timestamp(started_at),
        "ended_at": timestamp(ended_at),
        "planned_episode_ids": protocol["planned_episode_ids"],
        "episodes": episodes,
        "incidents": incidents,
    }
    unsigned["ledger_sha256"] = release_evidence.selected_hash(
        unsigned,
        (
            "candidate_commit",
            "protocol_sha256",
            "started_at",
            "ended_at",
            "planned_episode_ids",
            "episodes",
            "incidents",
        ),
    )
    unsigned["ledger_event_count"] = len(episodes) + len(incidents)
    payload = {
        "domain": "pgc-pilot-ledger-witness-v1",
        "candidate_commit": candidate_commit,
        "ledger_id": protocol["ledger_id"],
        "protocol_sha256": unsigned["protocol_sha256"],
        "ledger_sha256": unsigned["ledger_sha256"],
        "event_count": unsigned["ledger_event_count"],
        "completed_at": unsigned["ended_at"],
        "nonce": nonce,
    }
    key_path = release_evidence.safe_path(
        protocol_path.parent.resolve(), protocol["witness_public_key_path"]
    )
    return witness_request(
        kind="pilot_ledger",
        candidate_commit=candidate_commit,
        public_key_path=key_path,
        root=root,
        payload=payload,
        unsigned_artifact=unsigned,
    )


def assemble_pilot_source(
    *, output: Path, request_path: Path, signature_path: Path
) -> dict[str, Any]:
    request = load_object(request_path, "pilot witness request")
    if request.get("kind") != "pilot_ledger" or request.get(
        "request_sha256"
    ) != object_hash(request, "request_sha256"):
        raise SourceBuilderError("pilot witness request is invalid")
    signature = _load_signature(signature_path)
    key = release_evidence.load_bound_public_key(
        request_path.parent.resolve(),
        request["public_key_path"],
        request["public_key_sha256"],
        "pilot witness",
    )
    release_evidence.verify_signature(request["payload"], signature, key)
    source = {
        **deepcopy(request["unsigned_artifact"]),
        "ledger_receipt": {
            "payload": deepcopy(request["payload"]),
            "signature_base64": signature,
        },
    }
    if errors := external_source_errors(source):
        raise SourceBuilderError("pilot source schema failure: " + "; ".join(errors))
    return source


def parse_time(value: str) -> datetime:
    return release_evidence.parse_time(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    reviewer = commands.add_parser("reviewer-source")
    reviewer.add_argument("--config", type=Path, required=True)
    reviewer.add_argument("--manifest", type=Path, required=True)
    reviewer.add_argument("--calibration-set", type=Path, required=True)
    reviewer.add_argument("--declarations", type=Path, required=True)
    reviewer.add_argument("--completed-at", required=True)
    reviewer.add_argument("--output", type=Path, required=True)

    bilingual = commands.add_parser("bilingual-source")
    bilingual.add_argument("--reviewer-source", type=Path, required=True)
    bilingual.add_argument("--fluent-reviewer-id", action="append", required=True)
    bilingual.add_argument("--completed-at", required=True)
    bilingual.add_argument("--output", type=Path, required=True)

    seal = commands.add_parser("holdout-seal")
    seal.add_argument("--sealed-at", required=True)
    seal.add_argument("--public-case-count", type=int, required=True)
    seal.add_argument("--case-id", action="append", required=True)
    seal.add_argument("--ciphertext", type=Path, required=True)
    seal.add_argument("--case-schema", type=Path, required=True)
    seal.add_argument("--witness-public-key", type=Path, required=True)
    seal.add_argument("--authors", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)

    access = commands.add_parser("holdout-access-audit")
    access.add_argument("--seal", type=Path, required=True)
    access.add_argument("--events", type=Path, required=True)
    access.add_argument("--generated-at", required=True)
    access.add_argument("--output", type=Path, required=True)

    result = commands.add_parser("holdout-result")
    result.add_argument("--case-id", required=True)
    result.add_argument("--completed-at", required=True)
    result.add_argument("--automated-status", choices=["PASS", "FAIL"], required=True)
    result.add_argument("--hard-failure-code", action="append", default=[])
    result.add_argument("--transcript", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)

    prepare = commands.add_parser("prepare-holdout-attempt")
    prepare.add_argument("--case-id", required=True)
    prepare.add_argument("--result", type=Path, required=True)
    prepare.add_argument("--events", type=Path, required=True)
    prepare.add_argument("--seal", type=Path, required=True)
    prepare.add_argument("--issued-at", required=True)
    prepare.add_argument("--nonce", required=True)
    prepare.add_argument("--output", type=Path, required=True)

    assemble = commands.add_parser("assemble-holdout-attempt")
    assemble.add_argument("--request", type=Path, required=True)
    assemble.add_argument("--signature", type=Path, required=True)
    assemble.add_argument("--output", type=Path, required=True)

    holdout = commands.add_parser("holdout-source")
    holdout.add_argument("--seal", type=Path, required=True)
    holdout.add_argument("--access-audit", type=Path, required=True)
    holdout.add_argument("--result", type=Path, action="append", required=True)
    holdout.add_argument("--attempt", type=Path, action="append", required=True)
    holdout.add_argument("--revealed-at", required=True)
    holdout.add_argument("--completed-at", required=True)
    holdout.add_argument("--output", type=Path, required=True)

    host_identity = commands.add_parser("privacy-host-identity")
    host_identity.add_argument("--named-host", required=True)
    host_identity.add_argument("--environment-id", required=True)
    host_identity.add_argument("--storage-root", type=Path, required=True)
    host_identity.add_argument("--audit-id", required=True)
    host_identity.add_argument("--audit-public-key", type=Path, required=True)
    host_identity.add_argument("--captured-at", required=True)
    host_identity.add_argument("--output", type=Path, required=True)

    privacy_prepare = commands.add_parser("prepare-privacy-source")
    privacy_prepare.add_argument("--host-identity", type=Path, required=True)
    privacy_prepare.add_argument("--checks", type=Path, required=True)
    privacy_prepare.add_argument("--findings", type=Path, required=True)
    privacy_prepare.add_argument("--retention-days", type=int, required=True)
    privacy_prepare.add_argument("--completed-at", required=True)
    privacy_prepare.add_argument("--nonce", required=True)
    privacy_prepare.add_argument("--output", type=Path, required=True)

    privacy_assemble = commands.add_parser("assemble-privacy-source")
    privacy_assemble.add_argument("--request", type=Path, required=True)
    privacy_assemble.add_argument("--signature", type=Path, required=True)
    privacy_assemble.add_argument("--output", type=Path, required=True)

    pilot_protocol_command = commands.add_parser("pilot-protocol")
    pilot_protocol_command.add_argument("--preregistered-at", required=True)
    pilot_protocol_command.add_argument("--ledger-id", required=True)
    pilot_protocol_command.add_argument("--witness-public-key", type=Path, required=True)
    pilot_protocol_command.add_argument("--episode-id", action="append", required=True)
    pilot_protocol_command.add_argument("--output", type=Path, required=True)

    pilot_prepare = commands.add_parser("prepare-pilot-source")
    pilot_prepare.add_argument("--protocol", type=Path, required=True)
    pilot_prepare.add_argument("--episodes", type=Path, required=True)
    pilot_prepare.add_argument("--incidents", type=Path, required=True)
    pilot_prepare.add_argument("--started-at", required=True)
    pilot_prepare.add_argument("--ended-at", required=True)
    pilot_prepare.add_argument("--nonce", required=True)
    pilot_prepare.add_argument("--output", type=Path, required=True)

    pilot_assemble = commands.add_parser("assemble-pilot-source")
    pilot_assemble.add_argument("--request", type=Path, required=True)
    pilot_assemble.add_argument("--signature", type=Path, required=True)
    pilot_assemble.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    try:
        candidate = source_identity()
        if args.command == "reviewer-source":
            value = reviewer_source(
                output=args.output,
                config_path=args.config,
                manifest_path=args.manifest,
                calibration_set_path=args.calibration_set,
                declarations_path=args.declarations,
                completed_at=parse_time(args.completed_at),
            )
        elif args.command == "bilingual-source":
            value = bilingual_source(
                output=args.output,
                reviewer_source_path=args.reviewer_source,
                fluent_reviewer_ids=args.fluent_reviewer_id,
                completed_at=parse_time(args.completed_at),
            )
        elif args.command == "holdout-seal":
            value = holdout_seal(
                output=args.output,
                candidate_commit=candidate,
                sealed_at=parse_time(args.sealed_at),
                public_case_count=args.public_case_count,
                sealed_case_ids=args.case_id,
                ciphertext_path=args.ciphertext,
                case_schema_path=args.case_schema,
                witness_public_key_path=args.witness_public_key,
                authors_path=args.authors,
            )
        elif args.command == "holdout-access-audit":
            value = holdout_access_audit(
                output=args.output,
                candidate_commit=candidate,
                seal_path=args.seal,
                events_path=args.events,
                generated_at=parse_time(args.generated_at),
            )
        elif args.command == "holdout-result":
            value = holdout_result(
                output=args.output,
                candidate_commit=candidate,
                case_id=args.case_id,
                completed_at=parse_time(args.completed_at),
                automated_status=args.automated_status,
                hard_failure_codes=args.hard_failure_code,
                transcript_path=args.transcript,
            )
        elif args.command == "prepare-holdout-attempt":
            value = prepare_holdout_attempt(
                output=args.output,
                candidate_commit=candidate,
                case_id=args.case_id,
                result_path=args.result,
                events_path=args.events,
                seal_path=args.seal,
                issued_at=parse_time(args.issued_at),
                nonce=args.nonce,
            )
        elif args.command == "assemble-holdout-attempt":
            value = assemble_holdout_attempt(
                output=args.output,
                request_path=args.request,
                signature_path=args.signature,
            )
        elif args.command == "holdout-source":
            value = holdout_source(
                output=args.output,
                candidate_commit=candidate,
                seal_path=args.seal,
                access_audit_path=args.access_audit,
                result_paths=args.result,
                attempt_paths=args.attempt,
                revealed_at=parse_time(args.revealed_at),
                completed_at=parse_time(args.completed_at),
            )
        elif args.command == "privacy-host-identity":
            value = privacy_host_identity(
                output=args.output,
                named_host=args.named_host,
                environment_id=args.environment_id,
                storage_root=args.storage_root,
                audit_id=args.audit_id,
                audit_public_key_path=args.audit_public_key,
                captured_at=parse_time(args.captured_at),
            )
        elif args.command == "prepare-privacy-source":
            value = prepare_privacy_source(
                output=args.output,
                candidate_commit=candidate,
                host_identity_path=args.host_identity,
                checks_path=args.checks,
                findings_path=args.findings,
                retention_days=args.retention_days,
                completed_at=parse_time(args.completed_at),
                nonce=args.nonce,
            )
        elif args.command == "assemble-privacy-source":
            value = assemble_privacy_source(
                output=args.output,
                request_path=args.request,
                signature_path=args.signature,
            )
        elif args.command == "pilot-protocol":
            value = pilot_protocol(
                output=args.output,
                candidate_commit=candidate,
                preregistered_at=parse_time(args.preregistered_at),
                ledger_id=args.ledger_id,
                witness_public_key_path=args.witness_public_key,
                planned_episode_ids=args.episode_id,
            )
        elif args.command == "prepare-pilot-source":
            value = prepare_pilot_source(
                output=args.output,
                candidate_commit=candidate,
                protocol_path=args.protocol,
                episodes_path=args.episodes,
                incidents_path=args.incidents,
                started_at=parse_time(args.started_at),
                ended_at=parse_time(args.ended_at),
                nonce=args.nonce,
            )
        elif args.command == "assemble-pilot-source":
            value = assemble_pilot_source(
                output=args.output,
                request_path=args.request,
                signature_path=args.signature,
            )
        else:
            return 2
        write_private_new(args.output, value)
        print(
            json.dumps(
                {
                    "status": "pass",
                    "output": str(args.output),
                    "sha256": file_hash(args.output),
                },
                indent=2,
            )
        )
        return 0
    except (
        SourceBuilderError,
        release_evidence.ReleaseEvidenceError,
        campaign.CampaignError,
        json.JSONDecodeError,
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {"status": "fail", "error": f"{type(exc).__name__}: {exc}"},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
