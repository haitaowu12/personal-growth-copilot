# Independent model review and next delivery gates

Date: 2026-10-03. Status: advisory review completed; candidate remains unqualified.

[ChatGPT Pro review](https://chatgpt.com/c/6ac0aeb9-6d50-83e9-a811-e06a3570eba2)
used the visibly selected 6 Pro model, power 5 of 5, through the Codex in-app browser.
The approved attachment hash was
`fccbdd161c93c9f40c7f8037f8858319669a9e15aa401054eb4f8a2fc02eaae7`;
the response returned the attachment-only nonce and matching hash. It inspected
14 supplied files from candidate `b05124c` and reported running 13 tests whose
complete dependencies were present. Its full rendered response is retained locally
in `external-feedback/pro-review-2026-10-03.txt`, with submission/capture metadata in
the original handoff receipt. These local artifacts are excluded from distribution.

The review did not inspect the complete player, integration branch or release assets,
or observe learners or live tutor behavior. Its external learning research includes
abstract-only coverage for Renkl and Kestin. This document does not convert that
research into an effect estimate for this product.

## Accepted findings and repairs

| Finding | Disposition and local evidence |
| --- | --- |
| Returned review checklists alias the validation template | Reproduced in process; fixed in `ff8f7bf`. Returned items cannot mutate the expected contract. No cross-process bypass claim. |
| Duplicate topic JSON fields silently keep the last value | Reproduced at root and nested answer key; fixed recursively in `ff8f7bf` before review or HTML generation. |
| Supported large worksheets exceed the 2 MB reader bound | Reproduced using 20 concepts and completed Unicode notes in both UTF-8 and ASCII-escaped JSON. Reader now allows 32 MB; preparation/check/emission enforce the serialized budget. Existing differing outputs remain protected. The shipped 21-item worksheet was not size-affected. |
| Dossier hides subtitle, duration and review intervals | Displayed as immutable topic metadata in worksheet schema 1.1, with explicit claim-review guidance. Old worksheets require regeneration and reassessment. |
| Distributed authoring link points outside the archive | Packager rewrites the repository-specific link to the archive layout. Extracted-package test resolves all local links in distributed Markdown docs. |
| Duplicate visible choices are accepted | Validator rejects choices identical after Unicode normalization, case folding and whitespace normalization. Semantic ambiguity still requires review. |
| Builder checks size only after unbounded read | CLI now reads at most the topic byte limit plus one before validation. No out-of-memory experiment or broader resource-safety claim. |

Regression evidence: `external-feedback/final-regressions-before.log` reproduces
five failing cases across metadata, worksheet round-trip, duplicate choices and
archive links. The repaired review suite passes all 16 tests, including the actual
extracted portable CLI and permanent nonqualification assertion. Final full-suite
validation: 187 tests passed; repository validator and whitespace checks passed.
A fresh package and schema-1.1 dossier were built; all 21 review decisions remain
pending. These checks do not include a new integrated browser acceptance run.

## Content audit: accepted correction requirements, not human approval

Pro examined all 21 inventory items, 36 choices and feedback entries, 12 keys and
12 hints. All keys were defensible among their supplied choices. Hinted selection
success remains assisted practice, not independent writing performance.

The three source pages were also inspected locally through the in-app browser on
2026-10-03: [NASA Appendix C](https://www.nasa.gov/reference/appendix-c-how-to-write-a-good-requirement/),
[product verification](https://www.nasa.gov/reference/5-3-product-verification/), and
[product validation](https://www.nasa.gov/reference/5-4-product-validation/).
This does not establish the historical September inspection events or reuse approval.

| Items | Required treatment in the next version |
| --- | --- |
| 1–3: sources | Record precise sections, actual inspection date/state, limitations and applicable reuse terms. Expand Appendix C coverage to assumptions and unresolved values. |
| 4–6: obligation concept, diagnostic, practice | Preserve independently checkable obligations and limits; no key changes. |
| 7–8: obligation transfer, review | Label near-transfer practice accurately; improve implausible public distractors. Do not use teaching questions as protected outcomes. |
| 9: obligation writing | Accept justified allocation alternatives; the worked architecture is illustrative. |
| 10: measure concept | Distinguish justified provisional values marked for resolution from authorized baseline commitments. Preserve the prohibition on fabricated promises. |
| 11–14: measure questions | Keys remain supported. Selection of evidence and simplified tolerance arithmetic do not establish complete verification planning or uncertainty analysis. |
| 15: measure writing | Accept an adequate elapsed-time measurement, without requiring timestamp representation. |
| 16: purpose concept | Verification and validation answer different questions against different criteria; evidence and trials may overlap. |
| 17–20: purpose questions | Retain the keys and bounded conclusions. Intended purpose and acceptance basis distinguish validation, not merely participation by users. |
| 21: purpose writing | Require intended-use outcome, relevant conditions and observable success criteria, while avoiding a full-project-plan requirement. |

Also replace the subtitle's “prove” claim with a practice-oriented description.
Implement these as topic 1.0.1 with a fresh byte hash and 21-item human review;
retain topic 1.0.0 and its progress compatibility until that revision is explicit.
No teaching bytes or learner progress formats were changed in this tooling repair.

## Next three delivery slices

1. **Finish integration verification.** Apply these bounded tooling changes to the
   intended integration candidate without overwriting existing development work.
   Run its actual package and device/browser journeys, including keyboard access,
   denied storage, save/resume/export/import/clear and unsaved-work warnings. Evidence
   must identify that candidate's commit and hashes. Earlier Chromium receipts do
   not establish the current integrated candidate's behavior.
2. **Revise the lesson and measurement contract.** Make the corrections above and
   have an independent practitioner resolve all 21 items. The present 0–8 pilot
   rubric does not score intended-use reasoning. Recommended scope is all three
   concepts, with an additional explicitly anchored purpose criterion and a newly
   frozen score range. Alternatively retain 0–8 and narrow the learning claim to
   requirement writing. Never report that score as evidence for all three concepts.
3. **Rehearse one bounded feasibility protocol before recruitment.** Recommended
   first lane is the offline player and a single-arm usability rehearsal; a later
   parallel feasibility allocation can examine a bundle comparison descriptively.
   The owner must resolve lane, allocation, intended claim and deployment devices.
   A player study cannot validate conversational tutor guidance. Do not infer an
   efficacy effect from six to ten learners or from crossover counterbalancing.

The protocol freeze must define help versus accessibility accommodation; actual
exposure and time; prior experience; scoring anchors and defensible alternatives;
blinded artifact presentation and retained pre-adjudication ratings; a follow-up
window; delayed outcome **before** day-seven lesson review; intervening practice;
missingness with all enrolled learners in the denominator; consent, recipients,
retention and withdrawal handling; and an independent custodian for reserved tasks.
No reserved outcome questions should enter the implementation repository or tuning
conversation. Select named human content and outcome owners before recruitment.

A complete example followed by reduced support and independent application is a
reasonable future hypothesis. Defer extra topics, vector infrastructure, adaptive
engines and automatic promotion until the measurement gaps and observed learner
friction justify them. Tool tests, model critique and valid packaging establish
neither human approval nor production readiness, mastery or learning efficacy.
