All relative paths below are relative to the narration skill directory, one level above this reference.

# Podcasts and dialogue

[`example/podcast`](../example/podcast) is a short two-voice episode; build it
once to see every output.

## script.json

```json
{
  "id": "cache-talk", "title": "キャッシュの話",
  "cast": ["metan", "zundamon"],
  "speed": 1.05,
  "pauses": {"turn": 0.3},
  "bgm": {"file": "music.mp3", "gain": -24, "duck": true, "fade": 3},
  "chapters": [
    {"id": "c1", "title": "なぜ速くなるのか", "lines": [
      {"who": "zundamon", "text": "めたん、同じ計算を何度もすると遅いのだ。"},
      {"who": "metan", "text": "一度計算した結果を取っておけばいいのよ。", "style": "ツンツン"},
      {"text": "これがキャッシュ。", "pause": 0.8}
    ]}
  ]
}
```

- A chapter holds `lines`, or `scenes` each with `lines` (the video shape).
  A chapter `quiz` `{q, a, think?}` is spoken as two lines with the thinking
  time between them, as in a video.
- A line is a string or `{text, who?, style?, pause?, reading?, say?}`.
- `cast`: `"zundamon"` / `"metan"`, or `{"id", "speaker", "name"?}` with
  `speaker` ずんだもん or 四国めたん. `who` defaults to the previous line's
  speaker, at first the first member; `style` defaults to ノーマル (any talk
  style `yes-speak --list-speakers` shows). Without a cast, ずんだもん narrates.
- `id` names the output file (`out/<id>.m4a`); `title` and chapter titles go
  into the file's tags and chapter marks.

## Dialogue (掛け合い)

The roles and pacing that work in `zundamon-video` work without the picture:
one explains (めたん), one asks, guesses wrong and sums up (ずんだもん).
Switch speakers every 1–3 lines. Audio alone must carry everything, so name
what you refer to (never 「これ」「この図」) and say numbers in full. The
dialogue guide is [zundamon-video's authoring guide](../../zundamon-video/references/authoring.md).

## Pauses (間合い)

The pause after a line depends on what follows. Defaults, in seconds; set any
of them in `"pauses"`, or one line's `"pause"`:

| after a line, when next comes | key | default |
|---|---|---|
| a line by the same speaker | `line` | 0.35 |
| a line by another speaker | `turn` | same as `line` (0.3 suits a brisk dialogue) |
| a new scene | `scene` | 0.9 |
| a new chapter | `chapter` | 1.4 |
| nothing (the end) | `end` | 1.0 |
| the answer to a quiz question (thinking time) | `think` | 4.0 |
| silence before the first line | `lead_in` | 0.4 |

A line's own `pause` always wins. Video builds use the same table with
`turn` equal to `line`, so a script times the same in both.

## Mixing and export

`mix` joins the lines with their pauses at the voice's own 24000 Hz, so the
timeline is exact to the sample, then:

- with `"bgm"`, loops the music under the whole episode at `gain` dB,
  lowers it further while someone speaks (`duck`, sidechain compression),
  and fades it out over the last `fade` seconds. Music is optional; its
  license is yours to check, and it never enters the voice credits.
- normalizes loudness to −16 LUFS integrated (LUFS: loudness units relative
  to full scale, the EBU R128 measure podcast apps expect) with a −1.5 dB
  true peak, in two passes;
- encodes 44.1 kHz mono AAC in `.m4a` (default) or MP3 (`--format mp3`),
  `--bitrate` 64k by default, with the title, the voice credits as artist,
  and one chapter mark per chapter.

Beside it: `timeline.json` (each line's start and end), `transcript.md`
(speaker names, chapters, credits at the end) and `narration.raw.wav`.

## Credits for audio-only

VOICEVOX's voice terms need the credit where listeners will find it. A page
shows it next to the player; an audio file has no page, so:

- put `credits` output (`VOICEVOX:四国めたん`, `VOICEVOX:ずんだもん`) in the
  episode's show notes or description, and
- consider a spoken credit as the last line, as the example does.

The file's artist tag carries the credits too, but players may not show it.
Check the [voice terms](../../../THIRD_PARTY_NOTICES.md) for the intended
use before publishing.
