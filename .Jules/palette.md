## 2025-02-12 - Added character count and aria-describedby for textarea
**Learning:** The text area `draft` was missing ARIA descriptions and a character count, making it less accessible for screen readers and providing no feedback on the 4000 character limit.
**Action:** Always add live-updating character counters and use `aria-describedby` to link instructional text to input elements when max lengths are specified.
