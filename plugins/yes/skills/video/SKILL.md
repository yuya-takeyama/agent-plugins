---
name: video
description: Create a narrated HTML explainer with measured audio timing, synchronized captions, scene builds, chapters, and transcript. Use for a single-narrator explainer, not an MP4 export.
---

# video

Resolve all bundled paths from this SKILL.md file, never from a hard-coded
agent installation directory. The plugin root is two directories above this
skill. The complete `yes` plugin is the supported installation unit.

Write and revise local source files. Deliver a single self-contained HTML file
by default, or an HTML + assets bundle when requested. Keep essential viewing
features usable without network access or persistent storage. Do not upload,
publish, or change visibility unless requested. Review the actual rendered
output on desktop and mobile; report unavailable checks honestly.

Read [the authoring guide](references/authoring.md) for schemas and runtime behavior.

List primary references in `script.json` as `"sources": [{"title": "…",
"url": "https://…", "note": "optional"}]`. They appear as 出典 links in
the expandable description, including inside a course. `lint` and `build`
reject missing titles and URLs other than absolute HTTP(S) URLs.

Run `uv run <this-skill-dir>/build.py build <project-dir>`.
Add `--format bundle` for a sibling `<name>-bundle/index.html` and assets directory;
otherwise the output is one HTML file. `--max-bytes N` optionally enforces a host limit.

Audio uses the plugin's `../../bin/yes-speak` wrapper by default. It starts and
reuses a local Docker VOICEVOX Engine. Docker must be installed and running;
the first build downloads the engine image. See the plugin's
`../../README.md` for startup, voice selection, and stopping the engine.
`EV_TTS_CMD` can replace the command using the same flags and WAV contract.
For a single narrator, the bundled voice is credited automatically; set
`"credit"` in script.json when using a custom TTS command.

Run `lint`, then `build`, then `shoot`, and inspect every scene screenshot.
The screenshot command uses installed Chrome; `YES_BROWSER_CHANNEL=''` selects
Playwright Chromium instead. Review pronunciation and the standalone transcript.
Keep VOICEVOX credits in the generated page.
Read [voice and artwork conditions](../../THIRD_PARTY_NOTICES.md) before
selecting a voice or distributing its output. Preserve the generated usage
terms in the description. With `EV_TTS_CMD`, supply the adapter's actual
`usageTerms: {text, links: [{title, url, note}]}` in script.json along with its
credit; these are displayed without assuming the custom engine is VOICEVOX.
