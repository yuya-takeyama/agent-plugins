---
name: zundamon-video
description: Create a Japanese dialogue explainer with ずんだもん and 四国めたん using VOICEVOX, synchronized captions, and optional character art. Use for 掛け合い解説 or ずんだもん動画.
---

# zundamon-video

Resolve all bundled paths from this SKILL.md file, never from a hard-coded
agent installation directory. The plugin root is two directories above this
skill. The complete `yes` plugin is the supported installation unit.

Write and revise local source files. Deliver a single self-contained HTML file
by default, or an HTML + assets bundle when requested. Keep essential viewing
features usable without network access or persistent storage. Do not upload,
publish, or change visibility unless requested. Review the actual rendered
output on desktop and mobile; report unavailable checks honestly.

Read [the dialogue authoring guide](references/authoring.md), then the sibling
[video skill](../video/SKILL.md). Write `script.json` and `scenes.html` and build
them using `../video/build.py`. Read the bundled example before your first video.

Use inline cast members for portable voice-only dialogue. String members such
as `"metan"` select optional third-party character art and can download large
PSDs. Before enabling them, read the plugin's `../../THIRD_PARTY_NOTICES.md`
and respect the source artist's terms. Do not include downloaded art in this repo.

The narrator, caption timing, and build verification follow `video`. The delivered
HTML needs neither Docker nor VOICEVOX on the viewer's machine.
