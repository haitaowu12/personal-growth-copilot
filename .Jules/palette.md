## 2024-10-24 - Accessibility styling in vanilla JS UI
**Learning:** Re-used helper styles (`.meta`) correctly styled the progress-row component, but omitting them when wrapping elements can result in loss of visual hierarchy for A11y text.
**Action:** When adding structural wrappers, explicitly preserve existing typography classes (`.meta`) on text nodes to maintain visual coherence.
