## 2023-10-16 - O(n^2) nested array methods
**Learning:** Found O(n^2) array operations `.filter()` mixed with `.findIndex()` and `.some()` mixed with `.slice()` that slowed down the learner's local execution for generating summaries. The absence of `pnpm` workspace setup means using generic formatting tools (`prettier`) is required.
**Action:** Replace nested array search functions with O(n) sets and iterative state trackers for UI aggregation tasks. Ensure to not pollute the global Git scope with lock files when attempting tests.

## 2026-10-18 - Index session events once per summary
**Learning:** Filtering the full event history for each concept repeats work proportional to both the number of concepts and events. A map local to `summary` reuses each concept's event list without retaining stale state between calls. Prerequisite checks still inspect the prerequisite's own events.
**Action:** Reuse the grouped events for status and summary fields, preserve standalone status calls, and compare outputs across interleaved histories before accepting this optimization. Measure each caller separately; fewer array passes do not guarantee a speedup in every state.

## 2024-10-21 - Optimize summary generation to single pass iteration
**Learning:** Found multiple chained O(n) `.filter()`, `.some()`, and `.length` array operations per concept during `summary()` calculation in `core.js`. This repeated array scanning scales poorly when event arrays grow.
**Action:** Replaced chained array methods with a single iterative `for` loop that passes over `eventsByConcept.get(c.id)` exactly once per concept, computing all variables (`attempts`, `first_correct`, `assisted`, `writing_example_views`, `writing_after_example`, `written`, `reviewed`) simultaneously.
