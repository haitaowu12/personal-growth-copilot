# Learning improvement review — 2 October 2026

Personal Growth Copilot has a working educational alpha, but production readiness
still depends on independent content review, human learning evidence and broader
delivery acceptance. The most useful next change is to make the existing lesson
reviewable and improve how the tutor checks reasoning before expanding content.

## Current state, verified locally

- Published `origin/main`, refreshed on 2 October, remains `0223f99` (PR #11).
- The working development checkout is on `codex/complete-personal-growth-copilot`
  at `e3c3345`, three commits ahead of published main, with substantial tracked and
  untracked work. Those files were preserved; this slice uses an isolated branch
  `codex/learning-content-review` based on the committed `e3c3345` tree.
- The old September 7 next-steps note describes a clean main checkout. It is a
  historical planning baseline, not an accurate description of today's checkout.
- `docs/LEARNING_ACCEPTANCE.md` records a September 11 Chromium/file-origin run.
  That narrows the earlier browser gap, but does not establish current in-app,
  cross-browser, assistive-technology or human usability acceptance. No browser
  session was run for this change; the player and topic bytes are unchanged.
- The main checkout contains additional unfinished release, persistence and
  evaluation tooling. Presence of those files does not establish their acceptance.
  The review worksheet here is an authoring input, not a replacement for that
  work's independent content-review evidence contract.

## Findings and action

| Priority | Finding | Action and remaining limit |
|---|---|---|
| High | Source IDs and valid answer keys establish structure, not semantic fidelity. Review previously required manually assembling every item. | Implemented a portable generator covering three sources, three concepts, twelve questions and three writing tasks; all 21 start pending. Independent judgments remain required. |
| High | A correct choice or polished output can conceal weak reasoning. | Tutor guidance now selects a source revisit, rationale question or changed-assumption/boundary task from the observed gap. This is instruction-level guidance, not validated adaptive behavior. |
| High | Repeating visible lesson questions cannot establish unseen transfer. | Authoring recipe distinguishes teaching/review material from external reserved outcome tasks; exposes assumptions and rubric alternatives. No new held-out questions were generated or inspected. |
| Medium | The source-to-topic recipe was prose-only and lacked a worked intake. | Added a portable intake using the existing requirements pack and repeatable preparation, rendering and checking commands. An independent second-author usability test remains open. |
| Medium | Engineering activity substantially exceeds verified learner evidence. | Keep the next investment on content review and clean-host use, then the consented learning pilot. Do not add a vector service, more coaching infrastructure or automatic skill promotion to address an undemonstrated learning gap. |

## Lessons adopted from recent work

The immediate inputs are the maintained Second Brain method records, read locally:

- **28 September:** `resources/methods/knowledge-distillation/README.md`, from
  commit `ca77e216`. Preserve source reasoning, conditions, edition and actual
  coverage; a shorter article alone is not evidence of better learning.
- **29 September:** `docs/knowledge-usefulness-pilot-2026-09-29.md` and the
  adjacent evaluation/human-trial methods, from commit `d898b05c`. The report found
  no measured advantage in its selected discovery and application comparisons.
  The supplied-evidence application experiment bypassed retrieval; its six
  synthetic scenarios cannot establish human learning benefit. The practical
  adaptations are separate fidelity/performance checks, changed assumptions,
  explicit applicability limits, preserved null results and protected outcome
  tasks. This review read the report, not a new execution of its raw trials.
- **Earlier supporting source:** the retained INCOSE IS 2026 education source
  record and PDF text extract, especially pages 4 and 18. They motivate checking
  reasoning ownership and staged AI assistance. Conference presentation material
  is not a validated learning-effect estimate for this product.

These sources inform design hypotheses. Their results do not transfer automatically
to Personal Growth Copilot. No private source extracts, evaluation cases, learner
records or completed reviewer identities enter the distributable skill.

## Delivered and checked

- `references/topic-authoring.md`: source-to-task recipe, worked intake and review
  procedure, included in the explicit learning package allowlist.
- `scripts/review_learning.py` inside the skill: exact-byte-bound JSON worksheet,
  readable Markdown dossier, immutable item inventory, attributed judgments and
  explicit pending/revise/accept counts. Invalid records fail; acceptance remains
  self-declared and never grants qualification.
- `references/topic-learning.md`: targeted conversational teaching adaptation.
- Eleven new regression tests cover stale content, omissions/duplicates/altered
  keys, attribution, malformed records, literal rendering, input limits, output
  preservation and execution from an extracted package outside the repo.
- Full local suite: **182 tests passed**, including the shared Node learning
  reducer checks. Repository validation, skill structure and diff checks passed.
  No live model evaluation, new browser observation, independent content review
  or learner trial was performed. Hosted CI is not claimed.

Generated reviewer files belong under ignored `build/content-review/` or another
chosen private directory. They are reviewer inputs, not committed sign-off evidence.
The teaching topic remains `requirements-writing@1.0.0`; no scores or progress
formats were changed. A future semantic topic correction needs a new topic version
and fresh hash-bound review.

## Next execution order

1. Have an independent requirements practitioner inspect the 21-item packet,
   record supported judgments and resolve requested corrections. Identity and
   independence must be established separately from the worksheet.
2. Integrate this bounded branch with the existing development work after its own
   review. Preserve the additional package entries in the dirty checkout; do not
   replace its allowlist wholesale. Close hosted checks and broader browser/
   accessibility evidence on the actual integration candidate.
3. Observe a second author using the recipe and an external recipient using the
   distribution/recovery flow. The automated extraction test proves portability
   of the commands, not the human experience.
4. Freeze the existing learner pilot only after content and delivery gates close.
   Use independently scored immediate and delayed unfamiliar tasks; retain help,
   missing follow-up and corrections. Keep the existing full coaching gates open.
5. Make one content correction from an observed failure; compare matched tasks
   and preserve null outcomes before claiming an improvement or adding a topic.
