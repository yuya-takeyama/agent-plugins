# Compatibility

The supported distribution unit is the complete YES plugin. Skills have local
names (`slides`) and acquire a namespace (`yes:slides`) when the host loads the
plugin. Claude Code uses its manifest; Codex uses the portable Agent Plugins
manifest and a separate marketplace catalog. Cursor and Grok Bot use
`.cursor-plugin/marketplace.json` at the repository root and
`plugins/yes/.cursor-plugin/plugin.json`. All three catalogs reference the same
plugin directory, including its scripts and licenses.

The Cursor marketplace is named `yuya-plugins`, matching the Claude catalog.
`metadata.pluginRoot` is `plugins` and the YES entry's `source` is `yes`. The
per-plugin manifest points skills at `./skills/`. Those paths are relative and
do not use `..`. `minClientVersions` is unset, so the plugin is not hidden from
Grok Bot. The Cursor manifest does not bundle an MCP server. Speech stays on
the bundled Docker engine, or on the generic `YES_TTS_CMD` / `YES_TTS_FILES`
hooks already documented for YES.

Claude Code's manifest validator can check the Claude catalog and plugin
without installing them. `scripts/validate.py` checks that Cursor manifest
names, versions, and relative paths agree with the Agent Plugins and Claude
manifests. Full host installation and invocation must be checked separately
from that check. Plugin manifests do not install Docker, uv, Python, or a
browser on the user's behalf.

Initial release verification: Claude Code marketplace and plugin manifest
validation, the portable plugin's official JSON Schema, Chrome desktop/mobile
output playback and interaction, HTTP-served bundle assets, and real Docker
VOICEVOX synthesis have passed. Installation and skill invocation inside Claude
Code, Codex, Cursor, Grok Bot, or other agent hosts have not yet been tested
end to end. Cursor and Grok Bot support here is format-level. After the
manifests are on `main`, the public repository can be submitted at
<https://cursor.com/marketplace/publish> and, when a Grok Bot listing is
wanted, <https://x.ai/bot/marketplace/submit-a-plugin> (submit the GitHub
repository as a packaged plugin).

Other Agent Plugins clients may load the portable plugin. This repository does
not claim that all hosts have been tested. Agent Skills-only hosts must retain
the full plugin resource layout. No automatic standalone renaming installer is
provided in this initial release.

Single HTML uses embedded JavaScript, CSS and media. A host must permit scripts
and audio data URLs; its CSP, storage, size, and download restrictions still
apply. Multi-file hosts must serve the bundle directory with relative asset
paths intact. A local static server is recommended for bundle previews.

Persistent progress is browser-local and best effort. Sandboxed viewers may
allow only in-memory state. The default audio backend requires a running Docker
daemon and network access for the first image pull. No remote synthesis service
is contacted. Browser playback requires a user gesture.
