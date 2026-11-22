---
name: narration
description: Turn a Japanese script into VOICEVOX narration with ずんだもん and 四国めたん - readings, script lint, cached per-line synthesis recorded in narration.json, loudness and silence checks, credits, and multi-speaker podcasts exported as m4a or mp3. Use for ナレーション, 読み上げ, ポッドキャスト, audio-only explainers, or to check how a video script will be read aloud.
---

# narration

Resolve all bundled paths from this SKILL.md file, never from a hard-coded
agent installation directory. The plugin root is two directories above this
skill. The complete `yes` plugin is the supported installation unit.

This skill owns everything between a script and its audio: what each line
says (readings), the checks that catch misreadings before synthesis, speech
synthesis with a per-line cache, the narration record, the audio checks, and
joining lines into a podcast. The sibling `video` and `zundamon-video` skills
use the same code (`narration/`) and dictionary for their narration, so the
rules below apply to them unchanged.

Before writing a script meant to teach, plan it with the sibling `design`
skill. Write and revise local files; do not upload or publish unless asked.

## Project

```
<project>/script.json    chapters → (scenes →) lines; optional cast, pauses, readings, bgm
<project>/readings.json  optional {"表記": "よみ"} for this project
```

A video project's `script.json` is a valid project: `lint` and `spoken` work
on it directly. Schema, cast and pauses: [podcasts and dialogue](references/podcast.md).

## Workflow

```sh
N='/absolute/path/to/plugin/skills/narration'
uv run $N/narrate.py lint    <project>   # no audio: line length, 読点, unread English, spaces, numbers
uv run $N/narrate.py spoken  <project>   # out/spoken.md: caption and spoken text of every line
uv run $N/narrate.py build   <project>   # synth → check → mix → credits
uv run $N/narrate.py say 'TrueTime です'  # one string through the dictionary
```

`build` is `synth` (only lines whose voice, speed or spoken text changed;
→ `out/narration.json` and `out/narration/*.wav`), `check` (loudness,
silence inside a line, caption speed), `mix` (pauses, optional BGM, EBU R128
loudness → `out/<id>.m4a`, or `--format mp3`, with chapters, `timeline.json`
and `transcript.md`) and `credits`.

1. Write the script. Follow [reading rules](references/reading.md): what
   VOICEVOX does with spaces, English, numbers and units, and how to fix it
   with `readings.json`, a line's `say` or `reading`. Japanese terms of art
   follow [one form per term](../../references/terms-ja.md).
2. `lint` until every `warn:` is fixed or consciously accepted. `listen:`
   lines are patterns VOICEVOX may read in an unintended way; rewrite them
   or listen to them.
3. `spoken`, and read **every line** of `out/spoken.md`. This is how the
   TrueTime pause was found: the spoken text, not the caption, is what is read.
4. `build`. Then listen to every line marked 👂 in `spoken.md`, every line
   `check` reports, and the first minute of the mix. Fix readings and build
   again; only the changed lines are synthesized again.
5. Deliver the audio with its credits (`credits`): VOICEVOX's terms require
   the credit where listeners find it, in the show notes or a spoken credit.

## Speech sources

The bundled `../../bin/yes-speak` starts a local Docker VOICEVOX engine by
default. `YES_VOICEVOX_URL` points it at another engine instead, and
`YES_VOICEVOX_API=jobs` selects an API that synthesizes a whole script per
request. A command or agent-written WAV files work too. Table, contracts and
caching: [speech sources](references/engines.md).

Only ずんだもん and 四国めたん are supported. Read the plugin's
[voice conditions](../../THIRD_PARTY_NOTICES.md) before choosing a voice or
distributing the audio.
