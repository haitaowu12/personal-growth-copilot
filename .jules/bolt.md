## 2023-10-16 - O(n^2) nested array methods
**Learning:** Found O(n^2) array operations `.filter()` mixed with `.findIndex()` and `.some()` mixed with `.slice()` that slowed down the learner's local execution for generating summaries. The absence of `pnpm` workspace setup means using generic formatting tools (`prettier`) is required.
**Action:** Replace nested array search functions with O(n) sets and iterative state trackers for UI aggregation tasks. Ensure to not pollute the global Git scope with lock files when attempting tests.
