## 2023-10-16 - O(n^2) nested array methods
**Learning:** Found O(n^2) array operations `.filter()` mixed with `.findIndex()` and `.some()` mixed with `.slice()` that slowed down the learner's local execution for generating summaries. The absence of `pnpm` workspace setup means using generic formatting tools (`prettier`) is required.
**Action:** Replace nested array search functions with O(n) sets and iterative state trackers for UI aggregation tasks. Ensure to not pollute the global Git scope with lock files when attempting tests.

## 2023-10-18 - core.summary O(N) optimizations
**Learning:** The `summary` function in `core.js` was repeatedly filtering over `session.events` for every concept resulting in O(N^2) behavior on the number of events. Grouping events into a Map by concept before looping over concepts drops the execution time by roughly ~50%.
**Action:** Always precompute and index frequently filtered array properties within a single iteration block when mapping over data.
