---
name: explain
description: Create a self-contained, scrollable HTML explanation of a topic, mechanism, or decision. Use for an explainer page; use slides, video, quiz, or course for those formats.
---

# explain

Resolve all bundled paths from this SKILL.md file, never from a hard-coded
agent installation directory. The plugin root is two directories above this
skill. The complete `yes` plugin is the supported installation unit.

Write and revise local source files. Deliver a single self-contained HTML file
by default, or an HTML + assets bundle when requested. Keep essential viewing
features usable without network access or persistent storage. Do not upload,
publish, or change visibility unless requested. Review the actual rendered
output on desktop and mobile; report unavailable checks honestly.

Establish what the reader already knows and what they should be able to explain
or decide afterwards. Introduce the concrete problem before its terminology.
Use a small worked example, then explain the mechanism and its trade-offs.
Distinguish sourced facts from assumptions and include source links near claims.

Create `explanation.html` with inline CSS and JavaScript. Use system fonts and
inline SVG or embedded images; do not depend on a CDN. Use semantic sections,
readable text, visible focus indicators, and controls with accessible labels.
Add interaction only when changing a value or revealing a step aids understanding.
Include a brief question or prediction when it checks the central concept.

For a user-stepped presentation use the sibling `slides` skill. For narration
use `video`; for two-character narration use `zundamon-video`; for assessment
use `quiz`; for multiple lessons use `course`. These are choices of output
format, not mandatory steps for an ordinary explanation.

Check the explanation against the sources, then render it at desktop and phone
widths. Test the controls, keyboard focus, and absence of external resource
requests. Return the file and say which checks you completed.
