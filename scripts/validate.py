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
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "scripts"))

import system_profiles  # noqa: E402
import release_evidence  # noqa: E402

EXPECTED_TECHNIQUE_ONTOLOGY = {
    "PGC-BCT-001": ("BCIO:007008", "goal strategising BCT"),
    "PGC-BCT-002": ("BCIO:007004", "agree behaviour goal BCT"),
    "PGC-BCT-003": ("BCIO:007010", "action planning BCT"),
    "PGC-BCT-004": ("BCIO:007080", "prompt intended action BCT"),
    "PGC-BCT-005": ("BCIO:007058", "instruct how to perform a behaviour BCT"),
    "PGC-BCT-006": ("BCIO:007024", "self-monitor behaviour BCT"),
    "PGC-BCT-007": ("BCIO:007028", "social support BCT"),
    "PGC-BCT-008": ("BCIO:007299", "review behaviour goal plan BCT"),
}


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
    plugin_root = ROOT / "plugins/personal-growth-copilot"
    skill_root = plugin_root / "skills/personal-growth-copilot"
    skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    metadata = (
        skill_root / "agents/openai.yaml"
    ).read_text(encoding="utf-8")
    plugin = json.loads(
        (plugin_root / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
    )
    marketplace = json.loads(
        (ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
    )
    qualification = json.loads(
        (ROOT / "release/qualification.json").read_text(encoding="utf-8")
    )
    browser_package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    browser_lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
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
    calibration_set = json.loads(
        (ROOT / "evals/reviewer-calibration-set.json").read_text(encoding="utf-8")
    )
    learning_package_inventory = json.loads(
        (ROOT / "release/learning-package-files.json").read_text(encoding="utf-8")
    )
    technique_registry = json.loads(
        (
            ROOT
            / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/technique-registry.json"
        ).read_text(encoding="utf-8")
    )
    if "TODO" in skill:
        errors.append("SKILL.md contains TODO")
    if "Use only after explicit invocation" not in skill:
        errors.append("SKILL.md lacks explicit invocation rule")
    if "allow_implicit_invocation: false" not in metadata:
        errors.append("agents/openai.yaml does not disable implicit invocation")
    if "$personal-growth-copilot" not in metadata:
        errors.append("agents/openai.yaml default prompt lacks explicit skill invocation")
    if plugin.get("name") != "personal-growth-copilot":
        errors.append("plugin name mismatch")
    if plugin.get("version") != version:
        errors.append("plugin version mismatch")
    if browser_package.get("version") != version:
        errors.append("browser acceptance package version mismatch")
    if browser_lock.get("version") != version:
        errors.append("browser acceptance lock version mismatch")
    if browser_package.get("devDependencies") != {"playwright-core": "1.63.0"}:
        errors.append("browser acceptance dependency must remain exactly pinned")
    if (
        browser_lock.get("packages", {})
        .get("node_modules/playwright-core", {})
        .get("version")
        != "1.63.0"
    ):
        errors.append("browser acceptance lock does not pin playwright-core 1.63.0")
    if plugin.get("skills") != "./skills/":
        errors.append("plugin skills path mismatch")
    if any(field in plugin for field in ("apps", "hooks", "mcpServers")):
        errors.append("plugin declares an unbundled app, hook, or MCP server")
    entries = [
        entry
        for entry in marketplace.get("plugins", [])
        if entry.get("name") == "personal-growth-copilot"
    ]
    if len(entries) != 1:
        errors.append("marketplace must contain exactly one personal-growth-copilot entry")
    else:
        entry = entries[0]
        if entry.get("source") != {
            "source": "local",
            "path": "./plugins/personal-growth-copilot",
        }:
            errors.append("marketplace plugin source mismatch")
        if entry.get("policy") != {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        }:
            errors.append("marketplace plugin policy mismatch")
    instruction_files = [skill_root / "SKILL.md", *sorted((skill_root / "references").glob("*.md"))]
    for instruction_file in instruction_files:
        body = instruction_file.read_text(encoding="utf-8")
        referenced_resources = set(
            re.findall(r"`((?:references|scripts|assets)/[^ `]+)`", body)
        )
        for relative_path in sorted(referenced_resources):
            if not (skill_root / relative_path).is_file():
                errors.append(
                    f"{instruction_file.relative_to(skill_root)} resource is missing: "
                    f"{relative_path}"
                )
    if qualification.get("release") != version:
        errors.append("release version mismatch")
    if qualification.get("status") != "blocked":
        errors.append("qualification must remain blocked")
    if qualification.get("production_claim_allowed") is not False:
        errors.append("production claim must be false")
    browser_gate = qualification.get("required_gates", {}).get(
        "learning_browser_acceptance"
    )
    browser_contract = qualification.get("evidence_contract", {}).get(
        "learning_browser_acceptance", {}
    )
    if browser_gate != "pass-local-three-engine-file-origin":
        errors.append("learning browser gate must state its local three-engine scope")
    if browser_contract.get("status") != browser_gate:
        errors.append("learning browser evidence status differs from the gate ledger")
    if browser_contract.get("generator") != "scripts/run_learning_browser_acceptance.mjs":
        errors.append("learning browser evidence must name the canonical generator")
    deterministic_limits = qualification.get("evidence_contract", {}).get(
        "deterministic_controls", {}
    ).get("does_not_cover", [])
    if "browser runtime behavior" not in deterministic_limits:
        errors.append("deterministic qualification must exclude browser runtime behavior")
    required_gate_status = qualification.get("required_gates", {})
    missing_gate_statuses = [
        gate for gate in release_evidence.GATES if gate not in required_gate_status
    ]
    if missing_gate_statuses:
        errors.append(
            f"qualification ledger lacks canonical release gates: {missing_gate_statuses}"
        )
    if tuple(evidence_index.get("gates", {})) != release_evidence.GATES:
        errors.append("evidence index gates must match canonical verifier order")
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
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/evidence-source-ids.json"
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
    try:
        contract = system_profiles.load_contract()
    except (OSError, json.JSONDecodeError, system_profiles.SystemContractError) as exc:
        errors.append(f"governed system contract is invalid: {type(exc).__name__}")
        contract = None
    if contract is not None:
        if cases.get("required_systems") != list(system_profiles.SYSTEM_IDS):
            errors.append("evaluation suite systems differ from governed system contract")
        if set(system_profiles.profile_sha256()) != set(system_profiles.SYSTEM_IDS):
            errors.append("system profile hashes do not cover every governed system")
        if set(system_profiles.profile_bundle_sha256()) != set(system_profiles.SYSTEM_IDS):
            errors.append("system profile bundle hashes do not cover every governed system")
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
    reference_dir = ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/references"
    available = {path.name for path in reference_dir.glob("*.md")}
    if missing := sorted(required_references - available):
        errors.append(f"missing references: {missing}")
    schema = ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/growth-record.schema.json"
    if not schema.exists():
        errors.append("growth record schema missing")
    required_runtime = {
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/growth_record.py",
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/record_store.py",
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/persistent_record_store.py",
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/context_runtime.py",
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/evidence-source-ids.json",
        ROOT / "requirements/ci.in",
        ROOT / "requirements/ci.txt",
        ROOT / "package.json",
        ROOT / "package-lock.json",
        ROOT / "scripts/run_learning_browser_acceptance.mjs",
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
        ROOT / "evals/reviewer-calibration-set.json",
        ROOT / "evals/reviewer-calibration-set.schema.json",
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
        ROOT / "evals/outcome-observations.schema.json",
        ROOT / "evals/outcome-result.schema.json",
        ROOT / "evals/learning-content-review.schema.json",
        ROOT / "evals/learning-feasibility-observations.schema.json",
        ROOT / "evals/learning-feasibility-result.schema.json",
        ROOT / "evals/development-config.schema.json",
        ROOT / "evals/development_campaign.py",
        ROOT / "evals/results/DEVELOPMENT_CAMPAIGN_SCHEMA.json",
        ROOT / "evals/system-contract.json",
        ROOT / "evals/system-contract.schema.json",
        ROOT / "evals/system_profiles.py",
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/safety-state-machine.yaml",
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/references/resource-resolver-interface.md",
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/safety_runtime.py",
        ROOT / "scripts/run_deterministic_qualification.py",
        ROOT / "scripts/build_target_config.py",
        ROOT / "scripts/target_session_cli.py",
        ROOT / "scripts/campaign_cli.py",
        ROOT / "scripts/campaign_workspace.py",
        ROOT / "scripts/attempt_inventory_cli.py",
        ROOT / "scripts/build_development_config.py",
        ROOT / "scripts/development_campaign_cli.py",
        ROOT / "scripts/external_source_builder.py",
        ROOT / "scripts/outcome_evaluation.py",
        ROOT / "scripts/learning_feasibility.py",
        ROOT / "scripts/run_persistent_store_drill.py",
        ROOT / "scripts/persistence_authorization.py",
        ROOT / "scripts/release_readiness.py",
        ROOT / "scripts/apply_verified_release.py",
        ROOT / "scripts/verify_exact_head_ci.py",
        ROOT / "providers/codex_cli_adapter.py",
        ROOT / "providers/codex_cli_review_adapter.py",
        ROOT / "providers/codex-output.schema.json",
        ROOT / "providers/codex-review-output.schema.json",
        ROOT / "providers/README.md",
        ROOT / "docs/TARGET_EXECUTION.md",
        ROOT / "docs/DEVELOPMENT_EXECUTION.md",
        ROOT / "docs/PERSISTENT_STORE.md",
        ROOT / "docs/QUALIFICATION_OPERATIONS.md",
        ROOT / "docs/EXTERNAL_SOURCE_INPUTS.md",
        ROOT / "docs/OUTCOME_EVALUATION.md",
        ROOT / "docs/OUTCOME_EVIDENCE.md",
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
        ROOT / "release/release-readiness.schema.json",
        ROOT / "release/qualification-work-plan.schema.json",
        ROOT / "release/external-witness-request.schema.json",
        ROOT / "release/persistent-store-drill.schema.json",
        ROOT / "release/persistence-authorization.schema.json",
        ROOT / "release/persistence-authorization-request.schema.json",
        ROOT / "release/campaign-workspace.schema.json",
        ROOT / "release/campaign-workspace-status.schema.json",
        ROOT / "release/exact-head-ci.schema.json",
        ROOT / "release/verified-release-manifest.schema.json",
        ROOT / "release/trust-policy.json",
        ROOT / "release/evidence-index.json",
        ROOT / "scripts/release_evidence.py",
        ROOT / "scripts/release_packet.py",
        ROOT / "scripts/qualification_packet.py",
        ROOT / "scripts/host_privacy_discovery.py",
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/session-capsule.schema.json",
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/technique-registry.json",
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/technique-registry.schema.json",
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/references/session-capsule.md",
        ROOT / "examples/session-capsule.example.json",
    }
    for path in sorted(required_runtime):
        if not path.exists():
            errors.append(f"required runtime artifact missing: {path.relative_to(ROOT)}")
    for schema_path in (
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/growth-record.schema.json",
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
        ROOT / "evals/outcome-observations.schema.json",
        ROOT / "evals/outcome-result.schema.json",
        ROOT / "evals/reviewer-calibration-set.schema.json",
        ROOT / "evals/learning-content-review.schema.json",
        ROOT / "evals/learning-feasibility-observations.schema.json",
        ROOT / "evals/learning-feasibility-result.schema.json",
        ROOT / "evals/development-config.schema.json",
        ROOT / "evals/results/DEVELOPMENT_CAMPAIGN_SCHEMA.json",
        ROOT / "evals/system-contract.schema.json",
        ROOT / "providers/codex-output.schema.json",
        ROOT / "providers/codex-review-output.schema.json",
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
        ROOT / "release/release-readiness.schema.json",
        ROOT / "release/qualification-work-plan.schema.json",
        ROOT / "release/external-witness-request.schema.json",
        ROOT / "release/persistent-store-drill.schema.json",
        ROOT / "release/persistence-authorization.schema.json",
        ROOT / "release/persistence-authorization-request.schema.json",
        ROOT / "release/campaign-workspace.schema.json",
        ROOT / "release/campaign-workspace-status.schema.json",
        ROOT / "release/exact-head-ci.schema.json",
        ROOT / "release/verified-release-manifest.schema.json",
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/session-capsule.schema.json",
        ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/technique-registry.schema.json",
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
    calibration_schema = json.loads(
        (ROOT / "evals/reviewer-calibration-set.schema.json").read_text(
            encoding="utf-8"
        )
    )
    if list(
        Draft202012Validator(
            calibration_schema, format_checker=FormatChecker()
        ).iter_errors(calibration_set)
    ):
        errors.append("reviewer calibration set fails its schema")
    elif (
        calibration_set.get("holdout") is not False
        or calibration_set.get("system_identity_omitted") is not True
        or len(calibration_set.get("examples", [])) < 4
    ):
        errors.append("reviewer calibration set does not preserve its non-holdout blinded boundary")
    package_files = set(learning_package_inventory.get("files", []))
    if (
        "scripts/persistent_record_store.py" not in package_files
        or "scripts/record_store.py" not in package_files
        or "assets/technique-registry.json" not in package_files
        or "assets/technique-registry.schema.json" not in package_files
    ):
        errors.append(
            "learning/skill package inventory omits a governed record-store or technique-registry artifact"
        )
    technique_schema = json.loads(
        (
            ROOT
            / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/technique-registry.schema.json"
        ).read_text(encoding="utf-8")
    )
    technique_schema_errors = list(
        Draft202012Validator(
            technique_schema, format_checker=FormatChecker()
        ).iter_errors(technique_registry)
    )
    if technique_schema_errors:
        errors.append("technique registry fails its schema")
    else:
        techniques = technique_registry["techniques"]
        technique_ids = [technique["id"] for technique in techniques]
        if len(technique_ids) != len(set(technique_ids)):
            errors.append("technique registry ids must be unique")
        known_techniques = set(technique_ids)
        observed_ontology = {
            technique["id"]: (technique["bcio_id"], technique["bcio_label"])
            for technique in techniques
        }
        if observed_ontology != EXPECTED_TECHNIQUE_ONTOLOGY:
            errors.append(
                "technique registry BCIO identifiers and labels differ from the pinned ontology mapping"
            )
        known_barriers = {
            "clarity",
            "capability",
            "opportunity",
            "motivation",
            "initiation",
            "persistence",
            "feedback",
            "recovery",
        }
        observed_barriers: set[str] = set()
        for technique in techniques:
            observed_barriers.update(technique["candidate_barriers"])
            if technique["id"] in technique["alternatives"]:
                errors.append(f"technique may not name itself as an alternative: {technique['id']}")
            if not set(technique["alternatives"]).issubset(known_techniques):
                errors.append(f"technique has an unknown alternative: {technique['id']}")
            if not set(technique["evidence_source_ids"]).issubset(evidence_ids):
                errors.append(f"technique has an unknown evidence source: {technique['id']}")
        if observed_barriers != known_barriers:
            errors.append("technique registry must cover every governed barrier")
        if technique_registry["ontology"]["evidence_source_id"] not in evidence_ids:
            errors.append("technique registry ontology source is absent from provenance")
    capsule_schema = json.loads(
        (ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/session-capsule.schema.json").read_text(
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
        if comparator.get("system_id") != comparator_name:
            errors.append(f"comparator system_id mismatch: {comparator_name}")
        if comparator.get("status") != "governed-executable":
            errors.append(f"comparator must be governed executable: {comparator_name}")
        for field in (
            "same_model_required",
            "same_safety_policy_required",
            "same_context_access_required",
        ):
            if comparator.get(field) is not True:
                errors.append(f"comparator may not weaken {field}: {comparator_name}")
        if comparator.get("context_policy") != "READ_ONLY_USER_APPROVED":
            errors.append(f"comparator context policy mismatch: {comparator_name}")
        if comparator.get("memory_policy") != "DISABLED":
            errors.append(f"comparator memory must be disabled: {comparator_name}")
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
    if "learning-browser-${{ matrix.browser }}.json" not in workflow:
        errors.append("CI must upload per-engine learning browser acceptance artifacts")
    for browser in ("chromium", "firefox", "webkit"):
        if browser not in workflow:
            errors.append(f"CI browser matrix is missing {browser}")
    if "exact-head-ci.json" not in workflow:
        errors.append("CI must upload the exact-head qualification receipt")
    if "ubuntu-latest" in workflow:
        errors.append("CI runner label must not float on ubuntu-latest")
    for action in (
        "actions/checkout@",
        "actions/setup-python@",
        "actions/setup-node@",
        "actions/upload-artifact@",
    ):
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
