## 2026-10-18 - Document title updates in client-side routing
**Learning:** In single-page applications or views where navigation doesn't trigger a full page reload, screen reader users and tab managers lose context if the `<title>` isn't dynamically updated to reflect the new view state.
**Action:** Always update `document.title` when rendering a new primary view (e.g., from overview to a specific concept) to ensure accessibility and usability.
