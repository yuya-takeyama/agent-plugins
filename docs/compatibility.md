# Compatibility

The supported distribution unit is the complete YES plugin. Skills have local
names (`slides`) and acquire a namespace (`yes:slides`) when the host loads the
plugin. Claude Code uses its manifest; Codex uses the portable Agent Plugins
manifest and a separate marketplace catalog. Both catalogs reference the same
plugin directory, including its scripts and licenses.

Claude Code's manifest validator can check the catalog and plugin without
installing them. Full host installation/invocation must be checked separately
from schema validation. Plugin manifests do not install Docker, uv, Python,
or a browser on the user's behalf.

Initial release verification: Claude Code marketplace and plugin manifest
validation, the portable plugin's official JSON Schema, Chrome desktop/mobile
output playback and interaction, HTTP-served bundle assets, and real Docker
VOICEVOX synthesis have passed. Installation and skill invocation inside Claude
Code, Codex, or other agent hosts have not yet been tested end to end.

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
