All relative paths below are relative to the narration skill directory, one level above this reference.

# Reading rules

A line has two texts. `text` is what a viewer reads (caption, transcript).
The **spoken text** is what VOICEVOX receives. The build makes the spoken
text in this order (`narration/reading.py`, `spoken()`):

1. `reading`, when the line has one: the whole line as spoken, taken as
   written. The dictionary is not applied.
2. otherwise `say` (a replacement for the caption text, e.g. without a
   symbol the voice should skip), or else `text`, with the **readings
   dictionary** applied: this skill's `readings.json`, then the project's
   `readings.json`, then `script.json` `"readings"`, later ones winning.
   Longer surfaces are replaced first (`Claude Code` before `Claude`).
   An English surface matches only as a whole word (`AI` never fires inside
   `MAIN`); a number may stand right before it (`10GB`, `50ms`).
   A Japanese surface matches anywhere, even inside a longer word
   (`札` also rewrites `名札`), so make Japanese surfaces long enough.
3. Every space next to a Japanese character is removed. Only a space between
   two ASCII words stays (`Hello World`).

[`rules/cases.json`](../rules/cases.json) holds these rules as test cases.
Another engine that follows them (the private video pipeline's Node engine,
for example) runs the same cases.

## Spaces are not pauses

VOICEVOX stops at every space. Measured on VOICEVOX 0.25.2 (ずんだもん):
「トゥルータイム です」 takes 1.91 s and 「トゥルータイムです」 1.33 s: one
space added a 0.58 s break before the particle, heard as
「トゥルータイム〈一拍〉です」. Writers put that space in captions out of
habit (`TrueTime です`, `有料の Workers`), so step 3 removes it everywhere,
including inside readings values and `reading` / `say`.

- Write katakana compounds joined: `"commit wait": "コミットウェイト"`, not
  `コミット ウェイト`. `lint` reports a reading value or `say` / `reading`
  with spaces next to Japanese (it is dropped anyway; the warning says so).
- An English word followed by a particle runs on once the space is gone
  (`トゥルータイムです`). For a real break, use 、 or the line's `pause`.
- Every 、 is a pause. Three or more in one spoken line read haltingly;
  `lint` warns. Join a list with と, or split the sentence.

## English and abbreviations

VOICEVOX guesses at English: it may spell a word letter by letter or read it
as romaji. Every ASCII word of two or more letters left in the spoken
text is a `lint` warning: add it to `readings.json` or give the line a
`reading`.

`readings.json` here is the shared seed: common cloud, programming, data,
operations and unit words, in the form Japanese engineers say them
(`Kubernetes` クバネティス, `PostgreSQL` ポストグレスキューエル, `TrueTime`
トゥルータイム). Add a word here when it is general and its reading is
settled; a project-specific name belongs in the project's `readings.json`.
Values are kana, joined, with no spaces or letters (a test checks this).

The readings decide only the sound. Which form a term takes on screen
(katakana alone, Japanese, or English with a gloss on first use) follows
[one form per term](../../../references/terms-ja.md): an English+gloss term
shows the English in captions and speaks it in katakana through the readings.

## Numbers, dates, units

VOICEVOX reads Arabic numerals well, including large ones (`12000円` and
`1万2000円` came out identical) and dates with a slash (`11/22` sounds the
same as `11月22日`). These patterns changed length when rewritten, so they
are read some other way than intended. `lint` and `spoken` mark them
`listen:` / 👂:

| written | write instead |
|---|---|
| `3〜5人` | `3から5人` |
| `1/3` (a fraction) | `3分の1` (a slash is read like a date) |
| `10:30` | `10時30分` |
| `3x速い`, `1920x1080` | `3倍速い`, `1920かける1080` |
| `0.25.2` (a version) | listen; or a `reading` such as `バージョンれいてんにじゅうごてんに` |

- Units after a number read through the dictionary (`10GB` → 10ギガバイト,
  `50ms` → 50ミリびょう). A unit not in it is an unread-English warning.
- Years: `2026年` is read correctly. A bare year without 年 is a number.
- Counters with irregular readings (〜日, 〜分, 〜本) depend on the number;
  listen when the line is about the number itself.

## Review

`spoken` writes `out/spoken.md`: each line's caption, the spoken text where
it differs, and 👂 notes. Read all of it before the first full synthesis;
after `synth` it also shows each line's length. `check` then reports audio
that needs a listen: silence of 0.7 s or more inside one line (a space, a
symbol or a misreading), long silence at either end, clipping, and a line
6 dB or more away from the median level (whisper styles are quieter by
design). It also reports lines whose captions run faster than 7.5 characters
per second of speech (CPS, the caption reading speed): split or shorten them.
