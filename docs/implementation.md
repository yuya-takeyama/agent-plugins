# Initial YES extraction

## Agreed scope

Repository: yuya-takeyama/agent-plugins, public, with room for multiple plugins.
The first plugin is yes. Skills: explain, slides, quiz, video, zundamon-video,
course. Exclude diagramming, dataviz, design, and Stash publishing/capabilities.
Keep local editable sources and deliver portable HTML. Optional bundles split
embedded media into relative assets. No private repository history is included.

## Components

- Root catalogs: Claude Code and Codex distribution, same plugin directory.
- Skill directories: authoring instructions, templates, builders, examples.
- Plugin scripts: shared HTML output profiles and Docker VOICEVOX wrapper.
- Tests: runtime navigation, caption timing, audio contract, Docker ownership
  and lifecycle, offline browser behavior, and real Docker synthesis in CI.

## Implementation sequence

1. Copy only the selected source directories; rename runtime namespaces and
   remove host-specific publishing, URLs, storage calls, and external fonts.
2. Add yes-speak: versioned CPU image, loopback-only dynamic port, owned named
   container reuse, readiness/version checks, speaker lookup, validated WAV output.
3. Connect builders to the bundled speech command and shared output profiles.
4. Rewrite skill entrypoints and examples; document optional external art terms.
5. Validate catalogs, links, output formats and browser behavior; run Docker
   synthesis, publish to main, then monitor GitHub Actions.

## Review focus

Cold-start concurrency; foreign container name collision; unavailable Docker;
existing output preservation; relative asset resolution after moving bundles;
storage-disabled viewers; missing optional browser/TTS tools; external resources
and private endpoint references leaking into the public package.
