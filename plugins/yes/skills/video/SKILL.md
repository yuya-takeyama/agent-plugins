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

Before writing content, plan it with the sibling `design` skill: write
`learning-brief.md`, or reuse the one a course has already written.

Read [the authoring guide](references/authoring.md) for schemas and runtime behavior.
Japanese terms of art follow [one form per term](../../references/terms-ja.md).

List primary references in `script.json` as `"sources": [{"title": "…",
"url": "https://…", "note": "optional"}]`. They appear as 出典 links in
the expandable description, including inside a course. `lint` and `build`
reject missing titles and URLs other than absolute HTTP(S) URLs.

Tie every factual line to its source in `"claims"`: `{"line": "c1-2.0",
"source": 0, "quote": "the source's own words"}`, or `{"line", "derived": "<line
it restates or computes from>"}`, or `{"line", "fiction": true}` for a
character's made-up detail. `lint` warns on a line with a number and no entry,
but declare claims without numbers too (who did or said what). Before building,
run `uv run <plugin>/scripts/check_claims.py <project-dir>`: fix every NOT FOUND,
and tell the user which claims sit on unfetched sources so a person checks them.

Run `uv run <this-skill-dir>/build.py build <project-dir>`.
Add `--format bundle` for a sibling `<name>-bundle/index.html` and assets directory;
otherwise the output is one HTML file. `--max-bytes N` optionally enforces a host limit.

Narration (readings, script checks, speech synthesis, the audio track) is the
sibling [`narration` skill](../narration/SKILL.md)'s; this builder calls its
code. Follow its [reading rules](../narration/references/reading.md) when
writing lines: spaces next to Japanese are dropped, English needs a reading,
and some number forms need rewriting. Audio uses the plugin's
`../../bin/yes-speak` (a local Docker VOICEVOX Engine) by default; Docker must
be running and the first build downloads the engine image.
`YES_VOICEVOX_URL`, `YES_TTS_CMD` or `YES_TTS_FILES` select another source
([speech sources](../narration/references/engines.md)). A command is treated as
VOICEVOX unless `YES_TTS_ENGINE=other` declares a different engine; then set
`"credit"` (and `usageTerms`) in script.json. Never declare VOICEVOX output as
`other`.

After `lint` is clean, have the script reviewed by someone who did not write
it, a fresh subagent when the host has them, against the sibling `design`
skill's rubric. Apply every fix, cutting humor outside its places, and lint
again. Then run `build`, then `shoot`, and inspect every scene screenshot.
`check` drives the built page (maximize, fallback) and must print only `ok`.
The screenshot command uses installed Chrome; `YES_BROWSER_CHANNEL=''` selects
Playwright Chromium instead. Read every line of `out/spoken.md` (what VOICEVOX
was asked to say), listen to the lines it marks, and read the standalone transcript.
Keep VOICEVOX credits in the generated page.
Read [voice and artwork conditions](../../THIRD_PARTY_NOTICES.md) before
selecting a voice or distributing its output. Preserve the generated usage
terms in the description. With `YES_TTS_ENGINE=other`, supply the engine's actual
`usageTerms: {text, links: [{title, url, note}]}` in script.json along with its
credit; these are displayed without assuming the custom engine is VOICEVOX.
