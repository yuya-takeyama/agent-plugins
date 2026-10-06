# Yuya’s Agent Plugins

Portable plugins for coding agents. The first plugin is **YES — Yuya’s Explainer
Skills**: HTML explanations, slides, quizzes, narrated videos, and courses.

## Claude Code

```text
/plugin marketplace add yuya-takeyama/agent-plugins
/plugin install yes@yuya-plugins
```

Use `/yes:explain`, `/yes:slides`, `/yes:quiz`, `/yes:video`,
`/yes:zundamon-video`, or `/yes:course`. Plugin metadata provides the namespace;
individual skills retain short names.

## Codex

```sh
codex plugin marketplace add yuya-takeyama/agent-plugins
```

Open the plugin browser (`/plugins` in CLI, or Plugins in the desktop app),
select the `yuya-plugins` source and install `yes`. Start a new session and
select the YES skill from the skills/mention picker. Codex uses the same skill
sources and the `yes` plugin namespace.

## Other agents

Agent Plugins-compatible hosts can load `plugins/yes/plugin.json` and its
`skills/` directory. Follow the host's plugin installation instructions.
For Agent Skills-only hosts, retain the **whole plugin directory** so relative
script dependencies resolve, and configure discovery of its skills. Copying
only one skill folder is not supported. Standalone hosts may not add the `yes`
namespace; check for conflicting names. Compatibility beyond Claude Code and
Codex is format-level until listed as tested in [compatibility](docs/compatibility.md).

## YES

| Skill | Output |
| --- | --- |
| explain | Scrollable explanation with examples and sources |
| slides | Responsive slide deck with progressive reveals |
| quiz | Multiple-choice comprehension checks with feedback |
| video | Narrated HTML player with synchronized captions |
| zundamon-video | Japanese dialogue with Zundamon and Metan |
| course | Lessons combining video, slides, and quizzes |

The default output is one self-contained HTML file. Builders can optionally
separate embedded media into an HTML + assets bundle. Publication is always a
separate task. See [YES usage and local speech](plugins/yes/README.md).

## Repository layout

Each plugin lives under `plugins/<name>` and has its own version and manifest.
The root Claude Code and Codex catalogs point to those directories. Add future
plugins as new directories and catalog entries; they do not need to share YES's
name, release version, or runtime dependencies.

## Development

```sh
npm ci
npm test
python3 -m unittest discover -s tests -v
python3 scripts/validate.py
uv run plugins/yes/skills/video/test_build.py
claude plugin validate .
```

Behavioral browser tests and speech integration instructions are in
[verification](docs/verification.md). Generated media and downloaded character
art are not committed. See [third-party notices](THIRD_PARTY_NOTICES.md).

## License

Original code and skill instructions: MIT. External voice engines, voices,
character artwork, and dependencies retain their respective licenses.
