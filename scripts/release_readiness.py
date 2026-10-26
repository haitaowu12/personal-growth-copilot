#!/usr/bin/env python3
"""Report repo-side release completeness separately from external qualification."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_evidence  # noqa: E402

SCHEMA = ROOT / "release/release-readiness.schema.json"
WORK_PLAN_SCHEMA = ROOT / "release/qualification-work-plan.schema.json"

GATE_MACHINERY: dict[str, dict[str, Any]] = {
    "behavioral_qualification": {
        "artifacts": [
            "evals/target_session.py",
            "evals/campaign.py",
            "scripts/target_session_cli.py",
            "scripts/campaign_cli.py",
            "scripts/campaign_workspace.py",
        ],
        "external": "Execute every frozen target, ablation, and comparator run with calibrated human labels and no omitted attempts.",
    },
    "reviewer_attestation": {
        "artifacts": [
            "evals/reviewer-calibration-set.json",
            "evals/reviewer-calibration.md",
            "release/reviewer-identity-attestation.schema.json",
            "scripts/external_source_builder.py",
        ],
        "external": "Independent coordinators attest reviewer identity, independence, fluency, calibration, and actual review use.",
    },
    "attempt_inventory": {
        "artifacts": [
            "evals/attempt_inventory.py",
            "scripts/attempt_inventory_cli.py",
            "evals/attempt-witness-receipt.schema.json",
        ],
        "external": "A stateful authority witnesses every provider attempt and distributes the current head and event count out of band.",
    },
    "holdout": {
        "artifacts": [
            "release/holdout-seal.schema.json",
            "release/holdout-attempt.schema.json",
            "release/holdout-access-audit.schema.json",
            "scripts/external_source_builder.py",
        ],
        "external": "Independent authors create untouched cases after freeze and the witness signs complete access and attempt records.",
    },
    "privacy_preflight": {
        "artifacts": [
            "scripts/host_privacy_discovery.py",
            "plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/persistent_record_store.py",
            "scripts/run_persistent_store_drill.py",
            "scripts/external_source_builder.py",
        ],
        "external": "The named host demonstrates encryption, no-sync placement, backup/restore, lifecycle controls, bounded retention, and incident response under an independent audit witness.",
    },
    "bilingual_review": {
        "artifacts": [
            "evals/human-review.schema.json",
            "release/external-gate-source.schema.json",
            "scripts/external_source_builder.py",
        ],
        "external": "Fluent independent reviewers complete and attest every Chinese or mixed-language primary review without meaning or safety loss.",
    },
    "pilot": {
        "artifacts": [
            "release/pilot-protocol.schema.json",
            "scripts/external_source_builder.py",
            "evals/outcome-measures.json",
            "scripts/outcome_evaluation.py",
        ],
        "external": "Consenting participants complete the preregistered 10-20 episode, 28-56 day pilot with withdrawals, missingness, incidents, burden, dependence, and delayed observations retained.",
    },
    "independent_release_review": {
        "artifacts": [
            "release/gate-artifact.schema.json",
            "release/signed-receipt.schema.json",
            "scripts/release_packet.py",
            "scripts/release_evidence.py",
        ],
        "external": "The independent release reviewer examines the complete current evidence index and signs PASS, FAIL, or INVALIDATED after all prerequisite gates.",
    },
    "owner_promotion": {
        "artifacts": [
            "release/evidence-index.schema.json",
            "scripts/release_packet.py",
            "scripts/apply_verified_release.py",
        ],
        "external": "The owner signs promotion or decline only after every prerequisite receipt is current and passing.",
    },
}

WORK_PLAN_DETAILS: dict[str, dict[str, Any]] = {
    "behavioral_qualification": {
        "prerequisites": [],
        "commands": [
            "python scripts/campaign_workspace.py status --workspace <packet>/behavioral/workspace.json",
            "python scripts/campaign_cli.py aggregate --config <packet>/target/target-config.json --manifest <packet>/behavioral/result-manifest.json --output <packet>/behavioral/campaign-result.json",
            "python scripts/release_packet.py build-gate --gate behavioral_qualification --source <packet>/behavioral/campaign-result.json ...",
        ],
        "schema": "evals/results/CAMPAIGN_RESULT_SCHEMA.json",
        "builder": "scripts/campaign_workspace.py and scripts/campaign_cli.py",
        "observations": [
            "Every frozen run is executed on the restricted provider with no favorable retry omitted.",
            "Calibrated primary human reviewers label each turn and preserve hard failures.",
        ],
        "directory": "behavioral",
        "completion": "The exact 610-run manifest replays, conditional behavioral rules pass, and the behavioral authority signs the gate artifact.",
    },
    "reviewer_attestation": {
        "prerequisites": ["behavioral_qualification"],
        "commands": [
            "python scripts/external_source_builder.py reviewer-source --config <packet>/target/target-config.json --manifest <packet>/behavioral/result-manifest.json --calibration-set <packet>/review/reviewer-calibration-set.json --declarations <packet>/review/reviewer-declarations.json --completed-at <time> --output <packet>/review/reviewer-source.json",
            "python scripts/release_packet.py build-gate --gate reviewer_attestation --source <packet>/review/reviewer-source.json ...",
        ],
        "schema": "release/external-gate-source.schema.json#reviewerAttestation",
        "builder": "scripts/external_source_builder.py reviewer-source",
        "observations": [
            "A coordinator verifies each reviewer identity, independence, language fluency, and calibration before qualification labels.",
            "The declarations reference the exact external attestations and the builder derives actual use counts from the manifest.",
        ],
        "directory": "review",
        "completion": "The exact used reviewer set replays against results and the reviewer authority signs PASS.",
    },
    "attempt_inventory": {
        "prerequisites": ["behavioral_qualification"],
        "commands": [
            "python scripts/attempt_inventory_cli.py verify --config <packet>/target/target-config.json --index <packet>/attempts/index-final.json --manifest <packet>/behavioral/result-manifest.json --policy <packet>/trust-policy.json --expected-policy-sha256 <owner-hash> --expected-head-sha256 <witness-head> --expected-event-count <count> --output <packet>/attempts/verification.json",
            "python scripts/release_packet.py build-gate --gate attempt_inventory --source <packet>/attempts/verification.json ...",
        ],
        "schema": "evals/attempt-inventory-index.schema.json",
        "builder": "scripts/attempt_inventory_cli.py",
        "observations": [
            "A stateful external witness signs every provider start, finish, failure, final result, and campaign seal.",
            "The provider-access audit makes unrecorded access detectable or impossible and the witness distributes the current head independently.",
        ],
        "directory": "attempts",
        "completion": "Every run and attempt reconciles to the independent current head/count and the attempt-log authority signs PASS.",
    },
    "holdout": {
        "prerequisites": ["attempt_inventory"],
        "commands": [
            "python scripts/external_source_builder.py holdout-source --seal <packet>/holdout/holdout-seal.json --access-audit <packet>/holdout/access-audit.json --result <result> --attempt <attempt> --revealed-at <time> --completed-at <time> --output <packet>/holdout/holdout-source.json",
            "python scripts/release_packet.py build-gate --gate holdout --source <packet>/holdout/holdout-source.json ...",
        ],
        "schema": "release/holdout-seal.schema.json plus release/external-gate-source.schema.json#holdout",
        "builder": "scripts/external_source_builder.py holdout-*",
        "observations": [
            "Independent authors create and encrypt untouched cases after candidate freeze without candidate-author access.",
            "The holdout witness signs complete per-case attempt ledgers and access evidence.",
        ],
        "directory": "holdout",
        "completion": "Sealed coverage meets the frozen threshold, no candidate access occurred, every hard gate passes, and the holdout authority signs PASS.",
    },
    "privacy_preflight": {
        "prerequisites": [],
        "commands": [
            "python scripts/run_persistent_store_drill.py --storage-root <dedicated-empty-root> --named-host <host> --environment-id <environment> --output <packet>/privacy/persistent-store-drill.json",
            "python scripts/external_source_builder.py prepare-privacy-source --host-identity <packet>/privacy/host-identity.json --checks <packet>/privacy/checks.json --findings <packet>/privacy/findings.json --retention-days <days> --completed-at <time> --nonce <nonce> --output <packet>/privacy/signing-request.json",
            "python scripts/external_source_builder.py assemble-privacy-source --request <packet>/privacy/signing-request.json --signature <external-signature> --output <packet>/privacy/privacy-source.json",
        ],
        "schema": "release/privacy-host-identity.schema.json plus release/external-gate-source.schema.json#privacyPreflight",
        "builder": "scripts/host_privacy_discovery.py, scripts/run_persistent_store_drill.py, and scripts/external_source_builder.py",
        "observations": [
            "The named host demonstrates storage mapping, encryption, no-sync placement, backup/restore, correction/export/deletion, bounded retention, and incident response.",
            "The independent privacy witness signs the exact audit ledger and all high or critical findings are resolved.",
        ],
        "directory": "privacy",
        "completion": "All seven source-witnessed controls pass, unresolved high findings are zero, and the privacy authority signs PASS.",
    },
    "bilingual_review": {
        "prerequisites": ["reviewer_attestation", "behavioral_qualification"],
        "commands": [
            "python scripts/external_source_builder.py bilingual-source --reviewer-source <packet>/review/reviewer-source.json --fluent-reviewer-id <id> --completed-at <time> --output <packet>/bilingual/bilingual-source.json",
            "python scripts/release_packet.py build-gate --gate bilingual_review --source <packet>/bilingual/bilingual-source.json ...",
        ],
        "schema": "release/external-gate-source.schema.json#bilingualReview",
        "builder": "scripts/external_source_builder.py bilingual-source",
        "observations": [
            "At least two externally verified fluent reviewers complete every Chinese or mixed-language primary review.",
            "No meaning-changing switch or mistranslation of safety, consent, hypothesis, or correction status occurs.",
        ],
        "directory": "bilingual",
        "completion": "Exact review coverage and per-system agreement replay with zero meaning or safety failures and the bilingual authority signs PASS.",
    },
    "pilot": {
        "prerequisites": ["privacy_preflight", "behavioral_qualification", "bilingual_review"],
        "commands": [
            "python scripts/external_source_builder.py prepare-pilot-source --protocol <packet>/pilot/protocol.json --episodes <packet>/pilot/episodes.json --incidents <packet>/pilot/incidents.json --started-at <time> --ended-at <time> --nonce <nonce> --output <packet>/pilot/signing-request.json",
            "python scripts/external_source_builder.py assemble-pilot-source --request <packet>/pilot/signing-request.json --signature <external-signature> --output <packet>/pilot/pilot-source.json",
            "python scripts/outcome_evaluation.py analyze --observations <packet>/pilot/outcomes.json --output <packet>/pilot/outcome-result.json",
        ],
        "schema": "release/pilot-protocol.schema.json plus release/external-gate-source.schema.json#pilot",
        "builder": "scripts/external_source_builder.py pilot-* and scripts/outcome_evaluation.py",
        "observations": [
            "Ten to twenty consenting real episodes span 28 to 56 days and preserve withdrawals, non-attempts, missing reviews, incidents, burden, and dependence.",
            "The independent pilot witness signs the complete ledger and every stop-category incident remains visible.",
        ],
        "directory": "pilot",
        "completion": "The exact preregistered schedule replays, stop-category counts are zero for promotion, withdrawals/deletions are honored, and the pilot authority signs PASS.",
    },
    "independent_release_review": {
        "prerequisites": ["behavioral_qualification", "reviewer_attestation", "attempt_inventory", "holdout", "privacy_preflight", "bilingual_review", "pilot"],
        "commands": [
            "python scripts/release_packet.py build-gate --gate independent_release_review --source <independent-review-source> ...",
            "python scripts/release_evidence.py verify-index --packet-root <packet> --expected-index-sha256 <owner-current-index-hash>",
        ],
        "schema": "release/gate-artifact.schema.json and release/signed-receipt.schema.json",
        "builder": "scripts/release_packet.py",
        "observations": [
            "An independent reviewer inspects the complete current source packs, receipts, failure examples, missingness, and claim boundaries.",
        ],
        "directory": "review",
        "completion": "All seven evidence gates are current and passing and the independent release reviewer signs PASS rather than a model-generated judgment.",
    },
    "owner_promotion": {
        "prerequisites": ["independent_release_review"],
        "commands": [
            "python scripts/release_packet.py build-gate --gate owner_promotion --source <owner-decision-source> ...",
            "python scripts/apply_verified_release.py --packet-root <packet> --expected-index-sha256 <owner-current-index-hash> --output <packet>/promotion/release-manifest.json",
        ],
        "schema": "release/gate-artifact.schema.json, release/signed-receipt.schema.json, and release/evidence-index.schema.json",
        "builder": "scripts/release_packet.py and scripts/apply_verified_release.py",
        "observations": [
            "The owner reviews the independent recommendation and signs explicit promotion or decline after every prerequisite receipt.",
        ],
        "directory": "promotion",
        "completion": "The current index is PROMOTED, every receipt verifies, and the owner-bound release manifest is generated without changing historical evidence.",
    },
}


def source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("readiness clock must be timezone aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_report(generated_at: datetime | None = None) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    qualification = json.loads(
        (ROOT / "release/qualification.json").read_text(encoding="utf-8")
    )
    policy = json.loads(
        (ROOT / "release/trust-policy.json").read_text(encoding="utf-8")
    )
    index = json.loads(
        (ROOT / "release/evidence-index.json").read_text(encoding="utf-8")
    )
    if tuple(GATE_MACHINERY) != release_evidence.GATES:
        raise ValueError("release-readiness gate order differs from the canonical verifier")
    if tuple(index["gates"]) != release_evidence.GATES:
        raise ValueError("committed evidence-index gates differ from the canonical verifier")
    missing: list[str] = []
    gates = []
    pending = []
    for gate_id in release_evidence.GATES:
        specification = GATE_MACHINERY[gate_id]
        absent = [path for path in specification["artifacts"] if not (ROOT / path).is_file()]
        missing.extend(absent)
        evidence_status = index["gates"][gate_id]["status"]
        if evidence_status != "PASS":
            pending.append(gate_id)
        gates.append(
            {
                "gate_id": gate_id,
                "role": release_evidence.ROLE_BY_GATE[gate_id],
                "repo_status": "FAIL" if absent else "PASS",
                "evidence_status": evidence_status,
                "repo_artifacts": specification["artifacts"],
                "external_requirement": specification["external"],
            }
        )
    repo_complete = not missing
    promoted = index["overall_status"] == "PROMOTED"
    status = (
        "PRODUCTION_PROMOTED"
        if promoted and repo_complete
        else "REPO_COMPLETE_EXTERNAL_PENDING"
        if repo_complete
        else "REPO_GAPS"
    )
    report = {
        "schema_version": "1.0",
        "evidence_class": "release-readiness-report",
        "status": status,
        "candidate_commit": source_commit(),
        "generated_at": timestamp(generated_at),
        "repo_side_complete": repo_complete,
        "production_qualified": promoted,
        "qualification_status": qualification["status"],
        "trust_policy_status": policy["status"],
        "evidence_index_status": index["overall_status"],
        "gates": gates,
        "missing_repo_artifacts": sorted(set(missing)),
        "external_observations_pending": pending,
        "claim_limit": (
            "Repository-side completeness means the schemas, builders, operators, "
            "verification, acceptance, and promotion machinery exist. It does not "
            "convert missing independent observations, signatures, participants, "
            "host controls, or owner promotion into release evidence."
        ),
    }
    report["report_sha256"] = release_evidence.digest(report)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(report)
    )
    if errors:
        raise ValueError("release-readiness report failed its schema")
    return report


def build_work_plan(
    *,
    candidate_commit: str,
    qualification_plan_sha256: str,
    generated_at: datetime | None = None,
    hard_invariants: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    if tuple(WORK_PLAN_DETAILS) != release_evidence.GATES:
        raise ValueError("qualification work-plan gate order differs from verifier")
    gates = []
    for gate_id in release_evidence.GATES:
        detail = WORK_PLAN_DETAILS[gate_id]
        gates.append(
            {
                "gate_id": gate_id,
                "role": release_evidence.ROLE_BY_GATE[gate_id],
                "prerequisites": detail["prerequisites"],
                "repo_commands": detail["commands"],
                "source_schema": detail["schema"],
                "source_builder": detail["builder"],
                "external_observations": detail["observations"],
                "output_directory": detail["directory"],
                "completion_condition": detail["completion"],
            }
        )
    result = {
        "schema_version": "1.0",
        "evidence_class": "qualification-external-work-plan",
        "status": "AWAITING_EXTERNAL_OBSERVATIONS",
        "candidate_commit": candidate_commit,
        "generated_at": timestamp(generated_at),
        "qualification_plan_sha256": qualification_plan_sha256,
        "gates": gates,
        "execution_order": list(release_evidence.GATES),
        "hard_invariants": list(hard_invariants),
        "claim_limit": (
            "This work plan names exact repository operators and irreducible external "
            "observations. It creates no identity, independence, signature, holdout, "
            "host-control, participant, gate-passage, or promotion evidence."
        ),
    }
    result["work_plan_sha256"] = release_evidence.digest(result)
    schema = json.loads(WORK_PLAN_SCHEMA.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(result)
    )
    if errors:
        raise ValueError("qualification work plan failed its schema")
    return result


def write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("release-readiness output is create-only")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = build_report()
        if args.output:
            write_new(args.output, report)
        print(json.dumps(report, indent=2))
        return 0 if report["repo_side_complete"] else 1
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
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
