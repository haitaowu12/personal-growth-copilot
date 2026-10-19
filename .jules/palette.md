
## 2026-10-19 - SPA Context Updates for Screen Readers
**Learning:** In a single-page application (SPA), updating the URL or changing the main view content via client-side routing does not automatically announce the context change to screen readers, unlike full page reloads.
**Action:** Always dynamically update `document.title` on client-side route or view changes. This ensures screen readers announce the new context to users.
