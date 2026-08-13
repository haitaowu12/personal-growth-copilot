# Governance crosswalk: PGC, ICF AI coaching domains, and NIST AI RMF

Date: 2026-08-13
Status: gap map, not certification

The ICF AI Coaching Framework and current ICF Code of Ethics provide
professional governance signals. NIST AI 600-1 provides cross-sector generative
AI risk-management guidance. This crosswalk records where PGC controls exist,
what evidence is available, and which residual gaps remain. Mapping does not
establish ICF approval, professional credentialing, legal compliance, or NIST
certification.

| PGC control or invariant | ICF domain | NIST AI RMF function | Implementation | Evidence status | Residual gap / next evidence |
|---|---|---|---|---|---|
| Explicit invocation and agreed job/depth | Ethics; Relationship | GOVERN; MAP | `SKILL.md`, `PRODUCT_CONTRACT.md` | Contract and authored cases | Reference host must expose selected skill and test activation precision/recall. |
| Non-therapy, non-diagnostic scope | Ethics; Communication | GOVERN; MANAGE | `safety-and-scope.md`, safety state machine | Deterministic transition conformance only | Meaning-level host recognition and human-reviewed target runs remain absent. |
| Visible facts, hypotheses, alternatives, unknowns, corrections | Learning and Growth; Communication | MAP; MEASURE | `context-model.md`, growth-record schema | Schema and runtime conformance | Need ordinary-growth target runs and delayed correction outcomes. |
| User authorship of goals, scores, choices, and experiments | Relationship; Learning and Growth | GOVERN; MAP | context runtime and skill contract | Deterministic user-action gates | Named host must prove real user actions rather than model-authored attestations. |
| Technique eligibility, burden, and disconfirmation | Learning and Growth; Assurance and Testing | MAP; MEASURE | candidate technique registry | Candidate asset only | Codex must verify ontology mappings and integrate technique selection into target evaluation. |
| One material question and saturation | Communication; Relationship | MEASURE; MANAGE | context runtime | Conformance tests | Need naturalistic tests across models and prompt compositions; fixed threshold remains owner hypothesis. |
| Exact-delta consent, correction, export, deletion | Ethics; Technical Factors | GOVERN; MANAGE | record-store conformance | Non-persistent in-memory proof | Persistent named adapter, backups, deletion, and incident evidence are blocked. |
| Current-resource safety lookup | Ethics; Technical Factors | MAP; MANAGE | resource resolver interface | Failure-path conformance | No production resolver or jurisdiction coverage evidence exists. |
| Anti-dependence and real-world support | Relationship; Ethics | MAP; MEASURE; MANAGE | skill rules and rubric | Transcript-level authored cases | Pilot must measure exposure, reliance, human-support displacement, stopping, and withdrawal. |
| English/Chinese meaning preservation | Communication; Assurance and Testing | MEASURE | bilingual reference and Chinese cases | Authored cases only | Fluent independent reviewers, terminology calibration, and holdouts are pending. |
| Strong comparator and burden evaluation | Assurance and Testing | MEASURE | candidate comparator contracts and ordinary-growth suite | Candidate assets only | Integrate same-model/context comparisons and preregister outcome/burden analyses. |
| Provider/model/configuration provenance | Assurance and Testing; Technical Factors | GOVERN; MEASURE | target config, provider adapter, attempt inventory | Deterministic protocol conformance | Target execution and independent attempt witness remain unconfigured. |
| Separate target, holdout, privacy, pilot, review, and owner gates | Assurance and Testing; Ethics | GOVERN; MEASURE; MANAGE | release evidence protocol | Fail-closed protocol conformance | Real authorities, signatures, labels, holdouts, host evidence, pilot, and owner decision do not exist. |
| Incident and adverse-event preservation | Ethics; Assurance and Testing | MANAGE | pilot and release schemas | Schema/source-replay conformance | No real incident process has been exercised. |
| Accessibility and accommodation | Communication; Technical Factors | MAP; MEASURE | Mentioned in framework supplement | Open | Define accessibility requirements and test assistive technology, reading level, and non-text modalities before wider use. |

## Control rule

A documentation mapping cannot move an evidence gate. Each row needs an exact
implementation, execution result, accountable owner, and residual-risk decision
before it supports release. Unknown or unexecuted rows remain open rather than
being inferred from adjacent passing controls.
