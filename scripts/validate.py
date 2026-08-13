#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def canonical_hash(value: object) -> str:
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def validate_outcome_design(design: dict[str, object]) -> list[str]:
    errors: list[str] = []
    measures = design.get("measures", [])
    if not isinstance(measures, list):
        return ["outcome measures must be an array"]
    ids = [measure.get("id") for measure in measures if isinstance(measure, dict)]
    if len(ids) != len(set(ids)):
        errors.append("outcome measure ids must be unique")
    primary_ids = [
        measure.get("id")
        for measure in measures
        if isinstance(measure, dict) and measure.get("role") == "primary"
    ]
    if primary_ids != design.get("primary_outcome_ids"):
        errors.append("primary outcome ids must exactly match measures marked primary")
    if len(primary_ids) != 2:
        errors.append("exactly two primary outcomes must be preregistered")
    layers = {
        measure.get("layer")
        for measure in measures
        if isinstance(measure, dict)
    }
    if layers != {"process", "proximal", "delayed", "burden", "dependence"}:
        errors.append("outcome design must cover all five measurement layers")
    if design.get("qualification_claim_allowed") is not False:
        errors.append("outcome design must remain nonqualifying until execution")
    return errors


def validate() -> list[str]:
    errors: list[str] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    skill = (ROOT / "skill/personal-growth-copilot/SKILL.md").read_text(
        encoding="utf-8"
    )
    metadata = (
        ROOT / "skill/personal-growth-copilot/agents/openai.yaml"
    ).read_text(encoding="utf-8")
    qualification = json.loads(
        (ROOT / "release/qualification.json").read_text(encoding="utf-8")
    )
    trust_policy = json.loads(
        (ROOT / "release/trust-policy.json").read_text(encoding="utf-8")
    )
    evidence_index = json.loads(
        (ROOT / "release/evidence-index.json").read_text(encoding="utf-8")
    )
    evidence = json.loads(
        (ROOT / "provenance/evidence-sources.json").read_text(encoding="utf-8")
    )
    community = json.loads(
        (ROOT / "provenance/community-sources.json").read_text(encoding="utf-8")
    )
    cases = json.loads((ROOT / "evals/cases.json").read_text(encoding="utf-8"))
    outcome_design = json.loads(
        (ROOT / "evals/outcome-measures.json").read_text(encoding="utf-8")
    )
    if "TODO" in skill:
        errors.append("SKILL.md contains TODO")
    if "Use only after explicit invocation" not in skill:
        errors.append("SKILL.md lacks explicit invocation rule")
    if "allow_implicit_invocation: false" not in metadata:
        errors.append("agents/openai.yaml does not disable implicit invocation")
    if qualification.get("release") != version:
        errors.append("release version mismatch")
    if qualification.get("status") != "blocked":
        errors.append("qualification must remain blocked")
    if qualification.get("production_claim_allowed") is not False:
        errors.append("production claim must be false")
    if trust_policy.get("status") != "UNCONFIGURED" or trust_policy.get("authorities"):
        errors.append("committed release trust policy must remain unconfigured")
    if any(
        trust_policy.get(field) is not None
        for field in ("candidate_commit", "frozen_at", "attempt_campaign_id")
    ):
        errors.append(
            "committed release trust policy may not bind a candidate, freeze time, or attempt epoch"
        )
    policy_body = {key: value for key, value in trust_policy.items() if key != "policy_sha256"}
    if trust_policy.get("policy_sha256") != canonical_hash(policy_body):
        errors.append("release trust policy self-hash mismatch")
    if evidence_index.get("overall_status") != "BLOCKED":
        errors.append("committed release evidence index must remain blocked")
    index_body = {key: value for key, value in evidence_index.items() if key != "index_sha256"}
    if evidence_index.get("index_sha256") != canonical_hash(index_body):
        errors.append("release evidence index self-hash mismatch")
    if evidence_index.get("trust_policy_sha256") != trust_policy.get("policy_sha256"):
        errors.append("release evidence index does not bind the committed trust policy")
    if len(evidence.get("sources", [])) < 17:
        errors.append("at least 17 evidence sources required")
    evidence_ids: set[str] = set()
    evidence_urls: set[str] = set()
    for index, source in enumerate(evidence.get("sources", [])):
        for field in ("id", "type", "citation", "url", "runtime_use", "limitation"):
            if not source.get(field):
                errors.append(f"evidence source {index} lacks {field}")
        source_id = source.get("id")
        if source_id in evidence_ids:
            errors.append(f"duplicate evidence source id: {source_id}")
        evidence_ids.add(source_id)
        url = source.get("url", "")
        if not url.startswith("https://"):
            errors.append(f"evidence source {index} url must use https")
        if url in evidence_urls:
            errors.append(f"duplicate evidence source url: {url}")
        evidence_urls.add(url)
    evidence_runtime_index_path = (
        ROOT / "skill/personal-growth-copilot/assets/evidence-source-ids.json"
    )
    if not evidence_runtime_index_path.exists():
        errors.append("runtime evidence-source index missing")
    else:
        try:
            evidence_runtime_index = json.loads(
                evidence_runtime_index_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            errors.append("runtime evidence-source index is invalid JSON")
        else:
            if evidence_runtime_index.get("schema_version") != "1.0":
                errors.append("runtime evidence-source index schema version mismatch")
            runtime_ids = evidence_runtime_index.get("source_ids")
            if not isinstance(runtime_ids, list) or len(runtime_ids) != len(
                set(runtime_ids)
            ):
                errors.append("runtime evidence-source ids must be a unique array")
            elif set(runtime_ids) != evidence_ids:
                errors.append("runtime evidence-source index differs from provenance ledger")
    if cases.get("schema_version") != "2.0":
        errors.append("branchable evaluation schema version must equal 2.0")
    if len(cases.get("cases", [])) < 8:
        errors.append("at least eight branchable multi-turn cases required")
    if len(community.get("sources", [])) < 16:
        errors.append("at least 16 pinned community sources required")
    community_repositories: set[str] = set()
    for index, source in enumerate(community.get("sources", [])):
        commit = source.get("commit", "")
        if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
            errors.append(f"community source {index} lacks a full commit hash")
        repository = source.get("repository", "")
        if not repository.startswith("https://github.com/"):
            errors.append(f"community source {index} is not a GitHub repository")
        if repository in community_repositories:
            errors.append(f"duplicate community repository: {repository}")
        community_repositories.add(repository)
        if not source.get("license") or not source.get("role"):
            errors.append(f"community source {index} lacks license or role")
    required_references = {
        "collaborative-inquiry.md",
        "context-model.md",
        "values-goals-and-motivation.md",
        "behavior-change-experiments.md",
        "reflection-and-review.md",
        "memory-and-continuity.md",
        "record-store-contract.md",
        "safety-and-scope.md",
        "bilingual-dialogue.md",
        "evidence-ledger.md",
    }
    reference_dir = ROOT / "skill/personal-growth-copilot/references"
    available = {path.name for path in reference_dir.glob("*.md")}
    if missing := sorted(required_references - available):
        errors.append(f"missing references: {missing}")
    schema = ROOT / "skill/personal-growth-copilot/assets/growth-record.schema.json"
    if not schema.exists():
        errors.append("growth record schema missing")
    required_runtime = {
        ROOT / "skill/personal-growth-copilot/scripts/growth_record.py",
        ROOT / "skill/personal-growth-copilot/scripts/record_store.py",
        ROOT / "skill/personal-growth-copilot/scripts/context_runtime.py",
        ROOT / "skill/personal-growth-copilot/assets/evidence-source-ids.json",
        ROOT / "requirements/ci.in",
        ROOT / "requirements/ci.txt",
        ROOT / "scripts/lint_eval_manifest.py",
        ROOT / "evals/run.py",
        ROOT / "evals/schema.json",
        ROOT / "evals/config.schema.json",
        ROOT / "evals/results/RESULT_SCHEMA.json",
        ROOT / "evals/target_session.py",
        ROOT / "evals/campaign.py",
        ROOT / "evals/attempt_inventory.py",
        ROOT / "evals/attempt-event.schema.json",
        ROOT / "evals/attempt-witness-receipt.schema.json",
        ROOT / "evals/attempt-inventory-index.schema.json",
        ROOT / "evals/target-config.schema.json",
        ROOT / "evals/human-review.schema.json",
        ROOT / "evals/review-request.schema.json",
        ROOT / "evals/reviewer-calibration.md",
        ROOT / "evals/result-manifest.schema.json",
        ROOT / "evals/results/TARGET_RUN_SCHEMA.json",
        ROOT / "evals/results/CAMPAIGN_RESULT_SCHEMA.json",
        ROOT / "evals/configs/conformance.json",
        ROOT / "evals/baselines/direct_assistant.yaml",
        ROOT / "evals/baselines/structured_reflection.yaml",
        ROOT / "evals/comparators/strong_generalist.yaml",
        ROOT / "evals/comparators/minimal_visible_model.yaml",
        ROOT / "evals/outcome-measures.schema.json",
        ROOT / "evals/outcome-measures.json",
        ROOT / "safety/safety-state-machine.yaml",
        ROOT / "safety/resource-resolver-interface.md",
        ROOT / "skill/personal-growth-copilot/scripts/safety_runtime.py",
        ROOT / "scripts/run_deterministic_qualification.py",
        ROOT / "scripts/build_target_config.py",
        ROOT / "scripts/target_session_cli.py",
        ROOT / "scripts/campaign_cli.py",
        ROOT / "scripts/attempt_inventory_cli.py",
        ROOT / "providers/codex_cli_adapter.py",
        ROOT / "providers/codex-output.schema.json",
        ROOT / "providers/README.md",
        ROOT / "docs/TARGET_EXECUTION.md",
        ROOT / "docs/OUTCOME_EVALUATION.md",
        ROOT / "docs/RELEASE_EVIDENCE.md",
        ROOT / "release/gate-artifact.schema.json",
        ROOT / "release/signed-receipt.schema.json",
        ROOT / "release/trust-policy.schema.json",
        ROOT / "release/evidence-index.schema.json",
        ROOT / "release/external-gate-source.schema.json",
        ROOT / "release/holdout-seal.schema.json",
        ROOT / "release/holdout-result.schema.json",
        ROOT / "release/holdout-attempt.schema.json",
        ROOT / "release/holdout-access-audit.schema.json",
        ROOT / "release/privacy-host-identity.schema.json",
        ROOT / "release/host-privacy-discovery.schema.json",
        ROOT / "release/pilot-protocol.schema.json",
        ROOT / "release/reviewer-identity-attestation.schema.json",
        ROOT / "release/qualification-packet-plan.schema.json",
        ROOT / "release/qualification-external-intake.schema.json",
        ROOT / "release/trust-policy.json",
        ROOT / "release/evidence-index.json",
        ROOT / "scripts/release_evidence.py",
        ROOT / "scripts/release_packet.py",
        ROOT / "scripts/qualification_packet.py",
        ROOT / "scripts/host_privacy_discovery.py",
        ROOT / "skill/personal-growth-copilot/assets/session-capsule.schema.json",
        ROOT / "skill/personal-growth-copilot/references/session-capsule.md",
        ROOT / "examples/session-capsule.example.json",
    }
    for path in sorted(required_runtime):
        if not path.exists():
            errors.append(f"required runtime artifact missing: {path.relative_to(ROOT)}")
    for schema_path in (
        ROOT / "skill/personal-growth-copilot/assets/growth-record.schema.json",
        ROOT / "evals/schema.json",
        ROOT / "evals/config.schema.json",
        ROOT / "evals/results/RESULT_SCHEMA.json",
        ROOT / "evals/target-config.schema.json",
        ROOT / "evals/human-review.schema.json",
        ROOT / "evals/review-request.schema.json",
        ROOT / "evals/result-manifest.schema.json",
        ROOT / "evals/results/TARGET_RUN_SCHEMA.json",
        ROOT / "evals/results/CAMPAIGN_RESULT_SCHEMA.json",
        ROOT / "evals/attempt-event.schema.json",
        ROOT / "evals/attempt-witness-receipt.schema.json",
        ROOT / "evals/attempt-inventory-index.schema.json",
        ROOT / "evals/outcome-measures.schema.json",
        ROOT / "providers/codex-output.schema.json",
        ROOT / "release/gate-artifact.schema.json",
        ROOT / "release/signed-receipt.schema.json",
        ROOT / "release/trust-policy.schema.json",
        ROOT / "release/evidence-index.schema.json",
        ROOT / "release/external-gate-source.schema.json",
        ROOT / "release/holdout-seal.schema.json",
        ROOT / "release/holdout-result.schema.json",
        ROOT / "release/holdout-attempt.schema.json",
        ROOT / "release/holdout-access-audit.schema.json",
        ROOT / "release/privacy-host-identity.schema.json",
        ROOT / "release/host-privacy-discovery.schema.json",
        ROOT / "release/pilot-protocol.schema.json",
        ROOT / "release/reviewer-identity-attestation.schema.json",
        ROOT / "release/qualification-packet-plan.schema.json",
        ROOT / "release/qualification-external-intake.schema.json",
        ROOT / "skill/personal-growth-copilot/assets/session-capsule.schema.json",
    ):
        try:
            Draft202012Validator.check_schema(
                json.loads(schema_path.read_text(encoding="utf-8"))
            )
        except Exception as exc:
            errors.append(
                f"invalid JSON Schema {schema_path.relative_to(ROOT)}: {type(exc).__name__}"
            )
    growth_schema = json.loads(schema.read_text(encoding="utf-8"))
    if growth_schema.get("properties", {}).get("schema_version", {}).get("const") != "1.1":
        errors.append("growth record schema version must equal 1.1")
    for collection in ("evidence", "scales", "check_ins", "decisions"):
        if collection not in growth_schema.get("required", []):
            errors.append(f"growth record schema must require {collection}")
    outcome_schema = json.loads(
        (ROOT / "evals/outcome-measures.schema.json").read_text(encoding="utf-8")
    )
    if list(Draft202012Validator(outcome_schema).iter_errors(outcome_design)):
        errors.append("outcome measurement design fails its schema")
    errors.extend(validate_outcome_design(outcome_design))
    capsule_schema = json.loads(
        (ROOT / "skill/personal-growth-copilot/assets/session-capsule.schema.json").read_text(
            encoding="utf-8"
        )
    )
    capsule_example = json.loads(
        (ROOT / "examples/session-capsule.example.json").read_text(encoding="utf-8")
    )
    if list(
        Draft202012Validator(
            capsule_schema, format_checker=FormatChecker()
        ).iter_errors(capsule_example)
    ):
        errors.append("session capsule example fails its schema")
    for baseline_name in ("direct_assistant", "structured_reflection"):
        baseline = yaml.safe_load(
            (ROOT / f"evals/baselines/{baseline_name}.yaml").read_text(encoding="utf-8")
        )
        if baseline.get("system_id") != baseline_name:
            errors.append(f"baseline system_id mismatch: {baseline_name}")
        if baseline.get("same_safety_policy_required") is not True:
            errors.append(f"baseline may not weaken safety: {baseline_name}")
        if baseline.get("memory_policy") != "DISABLED":
            errors.append(f"baseline memory must be disabled: {baseline_name}")
    for comparator_name in ("strong_generalist", "minimal_visible_model"):
        comparator = yaml.safe_load(
            (ROOT / f"evals/comparators/{comparator_name}.yaml").read_text(
                encoding="utf-8"
            )
        )
        if comparator.get("comparator_id") != comparator_name:
            errors.append(f"comparator id mismatch: {comparator_name}")
        if comparator.get("status") != "design-only-unexecuted":
            errors.append(f"comparator must remain design-only: {comparator_name}")
        for field in (
            "same_model_required",
            "same_safety_policy_required",
            "same_context_access_required",
        ):
            if comparator.get(field) is not True:
                errors.append(f"comparator may not weaken {field}: {comparator_name}")
        if comparator.get("memory_policy") != "READ_ONLY_USER_APPROVED":
            errors.append(f"comparator context policy mismatch: {comparator_name}")
    lock_text = (ROOT / "requirements/ci.txt").read_text(encoding="utf-8")
    input_requirements = {
        (match.group(1).lower().replace("_", "-"), match.group(2))
        for line in (ROOT / "requirements/ci.in").read_text(encoding="utf-8").splitlines()
        if (match := re.match(r"^([A-Za-z0-9_.-]+)==([^\s]+)$", line))
    }
    locked_requirements = {
        (match.group(1).lower().replace("_", "-"), match.group(2))
        for line in lock_text.splitlines()
        if (match := re.match(r"^([A-Za-z0-9_.-]+)==([^\\\s]+)", line))
    }
    if not input_requirements.issubset(locked_requirements):
        errors.append("hash lock is missing a direct CI requirement")
    if lock_text.count("--hash=sha256:") < 2 * len(locked_requirements):
        errors.append("CI requirements are not fully hash-locked")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    if "--require-hashes" not in workflow:
        errors.append("CI dependency install must enforce requirements hashes")
    if "multiturn-harness-conformance.json" not in workflow:
        errors.append("CI must upload the multi-turn harness conformance artifact")
    if "ubuntu-latest" in workflow:
        errors.append("CI runner label must not float on ubuntu-latest")
    for action in ("actions/checkout@", "actions/setup-python@", "actions/upload-artifact@"):
        lines = [line for line in workflow.splitlines() if action in line]
        if not lines or any(f"{action}v" in line for line in lines):
            errors.append(f"CI action is missing or not commit-pinned: {action}")
    return errors


def main() -> int:
    errors = validate()
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
