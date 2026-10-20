# Evidence rebalancing: research-design integration

Origin: 2026-08-13. Integration review: 2026-10-20.
Status: inspectable candidate designs; governed execution and release remain blocked.

The original PR head was `26f244dbbd3dea73edd0d5139adac9b9cd8b1b93`, based on
`767fa96ca51116f916997d04a8cf3cff67ee9515`. This integration is reconciled onto
main `d0f9ae610ff1f36c5017c16eeadec7afe882feee`, which already contains the
canonical capsule contract, strong-generalist and minimal-visible-model
comparators, and the newer source-grounded learning work.

## Integration decisions

| Proposal | Current disposition |
| --- | --- |
| Eight technique entries | Retained as candidate selection and falsification aids in the canonical plugin package; source IDs, alternatives, count/event review windows, and claim limits are validated. |
| Historical capsule schema and example | Superseded by the stronger current schema/example, preserved unchanged. No old `retention.stored`, `memory_delta`, or `experiment` shape is introduced. |
| Historical strong-generalist baseline | Omitted as a duplicate; the current same-capability comparator remains unchanged, along with `minimal_visible_model`. |
| MI-informed and capsule comparators | Reconciled into `evals/comparators/`, using `comparator_id`, `status: design-only-unexecuted`, identical model/safety/context requirements, and `READ_ONLY_USER_APPROVED` memory. |
| Fourteen ordinary-growth cases | Retained as authored research with `candidate_not_integrated` status: not integrated into governed execution, target profiles, run identities, aggregation, or evidence gates. |
| Evidence and community supplements | Source-reviewed and corrected, but still candidate supplements. Proposed `runtime_decision` and donor dispositions do not promote an evidence record or approve installation. |
| Historical handoff | Original three files preserved byte-for-byte; `handoff/README.md` explains obsolete paths, contracts, commits, and evidence scope. |
| Qualification | Add design-asset validation as the ninth deterministic check; preserve all eight existing checks, including learning-pack validation. |

The current learning follow-through in `ROADMAP.md` remains the operational
priority. This bounded integration does not expand the adaptive learning engine
or change its acceptance gates.

## Technique registry and verified naming

The registry is
`plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/technique-registry.json`.
Each candidate records a barrier hypothesis, eligibility, contraindications,
minimum burden, expected and disconfirming signals, review window, alternatives,
source IDs, and required user choice. It is a selection aid, not an exhaustive
method list or a validated prescription. An unattempted or blocked action does
not test the prediction; attempted failures should prompt model revision rather
than rationalization.

The eight identifier/label pairs below were independently checked against the
[official Human Behaviour-Change Project ontology](https://github.com/HumanBehaviourChangeProject/ontologies/blob/84c5e071eb1ca32c47b4d5e10c89fa0967611c8c/BehaviourChangeTechniques/bcto.owl),
commit `84c5e071eb1ca32c47b4d5e10c89fa0967611c8c`,
`BehaviourChangeTechniques/bcto.owl` Git blob
`5d55eb949797a50689d979776d2514ced6088d01`.

| Registry entry | Ontology identifier | Verified label |
| --- | --- | --- |
| PGC-BCT-001 | BCIO:007008 | goal strategising BCT |
| PGC-BCT-002 | BCIO:007004 | agree behaviour goal BCT |
| PGC-BCT-003 | BCIO:007010 | action planning BCT |
| PGC-BCT-004 | BCIO:007080 | prompt intended action BCT |
| PGC-BCT-005 | BCIO:007058 | instruct how to perform a behaviour BCT |
| PGC-BCT-006 | BCIO:007024 | self-monitor behaviour BCT |
| PGC-BCT-007 | BCIO:007028 | social support BCT |
| PGC-BCT-008 | BCIO:007299 | review behaviour goal plan BCT |

This verification establishes identifier/label agreement at that pin only. It
does not establish technique eligibility, safety, selection quality, user fit,
or efficacy. The 281-technique/20-group count in the evidence supplement refers
to the published 2023 ontology version, not the current repository's size.

### Research references and runtime citations

The ontology's `evidence_source_id` remains research naming provenance and may
reference the candidate supplement. It is not a growth-record citation
allowlist. Per-technique `evidence_source_ids` are restricted to IDs present in
both the canonical evidence ledger and
`plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/evidence-source-ids.json`.
The BCTO candidate stays in ontology metadata; it is not promoted into either
canonical source file. Registry status and eligibility remain unvalidated.

Active experiment cards use ordinary-language ingredients. Registry/BCIO IDs
belong in research or evaluation traceability, not growth-record citation
fields. Optional external citations use admitted `source_citation_id` values
inside `EXTERNAL_SOURCE` evidence items; hypothesis evidence references use
record-local item IDs. The record CLI loads the canonical `source_ids` array
and rejects candidate-only, taxonomy, and unknown citation IDs. Design-asset
validation of research metadata cannot authorize persistence or source admission.

## Canonical capsule and comparison contract

The existing schema remains at
`plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/session-capsule.schema.json`,
with `examples/session-capsule.example.json` as a preview. It preserves user
wording, source-tagged facts, hypotheses, alternatives, unknowns, choice,
prediction, disconfirmation, review point, open question, and the exact proposed
delta. It does not require an extra experiment or old retention object.

`persistence.status` is `not_requested`, `previewed`, or `confirmed_by_host`.
The first two have a null `host_receipt_sha256`; `previewed` is not a write.
Only an actual verified host result permits `confirmed_by_host` with its receipt
hash. The checked-in example must not claim a write. Preparation and later
retrieval require an explicit request and bounded purpose; retained content is
untrusted data and cannot override a current correction.

All four comparator designs require the same model, safety policy, and approved
context access. The MI-informed arm describes nonclinical reflective dialogue,
not a verified treatment. The capsule arm adds an explicitly requested preview
to direct assistance. It has no write privilege; a future write-enabled study
needs a common frozen host contract. Existing direct and structured-reflection
baselines remain ablations.

The four definitions are not executable slots. Before use, extend and freeze
suite schemas, target configuration, provider profiles, run identities, result
schemas, aggregation, blinded review, and the complete attempt inventory. Do
not relabel a design-asset check as comparator behavior evidence.

## Research cases and outcomes

The 14 cases cover decisions, learning, opportunity barriers, negative results,
outcome bias, non-action, directness, stale context, measurement burden,
Chinese-language meaning, recovery, and independent use. Case-level proposed
outcomes and delayed follow-ups are evaluation designs; they do not replace the
two primary outcome IDs in `evals/outcome-measures.json` or prove outcomes.

Keep five measurement layers separate:

1. Process: correction, material inquiry, evidence separation, and fit.
2. Proximal outcomes: user-confirmed clearer choice or better-specified uncertainty.
3. Delayed observations: attempts, non-attempts, dropout, model updates, and transfer.
4. Burden: turns, questions, disclosure, tracking, and time.
5. Dependence: stopping, real-world support, displacement, and independent choice.

The candidate suite requires delayed reviews in at least half its cases and at
least two Chinese or mixed-language cases. These structural coverage checks are
not human assessments of language quality or outcome validity. No aggregate
score can waive safety, privacy, dependence, fabricated-resource, or
fabricated-persistence failures.

## Source review and limitations

`research/evidence-rebalancing-update-20260813.md` records the primary-source
access and corrected interpretation. The 2025 and 2026 coaching studies differ
in interventions, samples, duration, and outcomes; they are not direct
replications or a pooled product-efficacy result. Attrition, nonsignificant
contrasts, study-internal inconsistencies, and limited transfer remain visible.

All six donor pins and their relevant README/license files were reviewed. The
Letta pin describes a legacy server whose active development moved elsewhere;
Mem0 distinguishes managed-platform benchmark claims from its open-source SDK.
Historical star/fork/last-push observations are not reverified current signals.
No donor implementation was exhaustively audited, copied, installed, or approved
by this review. Mixed-license and AGPL donors remain architecture-only.

## Verification and outstanding evidence

Run `scripts/validate_design_assets.py` for schemas, local references, comparator
parity, research coverage, source identity, and claim-boundary structure. It
returns structured errors for missing or malformed JSON/YAML/schema inputs and
does not fetch external schema references. Its mutation tests cover invalid
assets, dangling references, duplicate IDs, parity drift, false example
persistence, and coverage loss.

Run `scripts/run_deterministic_qualification.py` on the exact clean candidate
for all nine checks and a hash-bound local evidence file. These checks do not
use GitHub Actions. Historical handoff results do not qualify this candidate.

Target-model execution, independent holdouts, calibrated English/Chinese human
review, named-host privacy/security evidence, consented delayed observation,
and owner promotion remain separate gates. This integration does not install
or register the skill, enable implicit invocation, provision trust authorities,
initialize sensitive state, implement the reference host, or claim ICF/NIST
certification, human equivalence, or coaching efficacy.
