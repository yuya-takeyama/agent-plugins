All commands and relative resource paths below are relative to the owning skill directory, one level above this reference. `<PLUGIN>` is the directory containing `plugin.json`.

# zundamon-video

A dialogue video is a `video` project whose `script.json`
has a `"cast"`. The engine, scene kit, player and build commands are that
skill's; read its SKILL.md for `scenes.html` (`data-at`, `data-focus`, kit
classes) and the page behavior. This skill covers what changes when two
characters talk: who says what, how they sound, how they look, and where the
board leaves room for them.

```sh
S='/absolute/path/to/plugin/skills/video'
uv run $S/characters.py fetch metan       # once per machine: 立ち絵 PSD → ~/.cache (not in git)
uv run $S/characters.py fetch zundamon
uv run $S/build.py lint  <project>        # also checks who / face / style against the voices
uv run $S/build.py build <project>        # → out/video.html (audio cached per line and style)
uv run $S/build.py shoot <project>        # → out/frames/<scene>.png, then LOOK at them
uv run $S/build.py unit  <project> --id ID --out DIR   # for course
yes-speak --list-speakers                # every VOICEVOX character, style and id
```

`example/` is a complete 2-chapter video (空はなぜ青い), about 2 minutes:
both characters, eight of the nine faces, two non-normal styles, quizzes,
builds and SVG diagrams. Read its `script.json` and `scenes.html` before a first video.

Needs Docker running, the bundled `../../bin/yes-speak`, `uv`, and Google Chrome for `shoot`. The example uses voice-only inline cast members. Optional string cast members fetch missing artwork; read the third-party notices before opting in.

## Roles

- **四国めたん explains.** She holds the mechanism and the corrections.
- **ずんだもん asks and misreads.** He voices the learner: the likely
  misconception, the naive question, the paraphrase that checks
  understanding. He is never a second lecturer.
- Cast order is `["metan", "zundamon"]`. The first member is the explainer
  and the default speaker for lines and quiz lines; めたん stands left and
  ずんだもん right.

## Writing the 掛け合い

Everything in `video` about substance still holds: teach
what the thing is and why it works, the problem it solves, trade-offs; no
meta (which chapter covers what, how something was announced, item counts);
voice carries the logic, the board carries the structure, never 「この図」.
The dialogue adds these rules:

1. **Open with a つかみ, not with the lesson.** See [The opening](#the-opening-つかみ).
2. **Switch speakers every 1–3 lines.** めたん may run up to 4 lines while
   walking through a mechanism; then ずんだもん reacts or asks.
3. **Cycle:** 問い → 解説 → ずんだもん's reaction or paraphrase → めたん's
   ツッコミ or refinement. The paraphrase is the learning check, so make it
   a real restatement, not 「なるほどなのだ」.
4. **Two caption lines per utterance**, about 40 characters. Lint warns past
   that; split the sentence or give part of it to the other character.
5. **Humour is seasoning.** One small ズレ every 30–60 s, one sentence, never
   on the line that carries the key point. Cheap in-character gags:
   めたん's 金欠 and 中二病, ずんだもん being ないがしろにされる.
6. **Chapters** of 2–4 minutes. Each ends with a one-line ずんだもん summary,
   then the quiz. Quiz questions are usually めたん's (`q_who`); letting
   ずんだもん answer (`a_who`) shows he got it.
7. **No subscribe prompts, no thanks-for-watching card.** End on the last
   quiz or a one-line ずんだもん wrap-up. If the opening skit left something
   hanging, close it in the last scene in one exchange, ideally with the
   lesson's own words (the borrowed 千円 is 語りうる, so it gets repaid).

### The opening (つかみ)

Open with a short exchange connected to the topic. Avoid an unrelated skit that delays the explanation.

Its own first scene (`<ch>-0`), 5–7 lines, 20–35 s, in this order:

| # | who | does | face / style |
|---|---|---|---|
| 1 | either | calls the other by name (「ねえずんだもん」「めたん、聞いてほしいのだ」) and puts the topic's word or situation in the first line | normal / smile |
| 2 | the other | reacts, with the video's one in-character gag | jito, troubled; めたん may use ツンツン |
| 3 | ずんだもん | says the topic (the quote, the claim, the thing) — often by misusing it | smile / think |
| 4 | めたん | places it in one sentence: whose, what, where | surprised → normal |
| 5 | めたん | title call and goal: 「今回は〜を解説するわ。見終わるころには〜」 | smile / normal |
| 6 | ずんだもん | the misreading hook, which the next scene starts correcting | smile |

- Avoid repeating introductions in every course lesson. Open with a 呼びかけ.
- No spoken table of contents; the chapter bar does that. No
  「ゆっくりしていってね」 equivalent; the misreading is the cue.
- The best skit acts out the misconception itself. In the 論理哲学論考 video
  ずんだもん answers めたん's request to repay 千円 with
  「……語りえぬものについては、沈黙しなければならないのだ」 — the misuse the
  video then takes apart.
- Board: a small prop for the skit (an IOU, a receipt), then at the title
  call the topic itself, large, with the goal as a pill. Swap them with
  `ev-stack` + `data-out` / `data-at`.

### How each one talks

| | ずんだもん | 四国めたん |
|---|---|---|
| 一人称 | ボク | わたくし |
| 語尾 | 〜のだ / 〜なのだ | 〜わ / 〜かしら / 〜わよ / 〜ね |
| 口調 | 素直、ちょっと調子に乗る | お嬢様風のタメ口、少しツンデレ |

Not every clause ends in のだ: once per line at most, and a short line
(「6倍も！」) can drop it. The repetition grates in synthesized speech.

## Faces

Set `face` on a line when the expression should change; it sticks for that
character until their next `face`. The listener keeps the face from their
last line, so set it on the line that earns it. Quiz lines take no `face`:
the asker keeps the face of their last line, so end a chapter on a face that
suits asking (a `jito` ツッコミ right before the quiz carries into it).

| face | when |
|---|---|
| `normal` | default; めたん's explaining face |
| `smile` | わかった / すごい, a good paraphrase, めたん's recap |
| `surprised` | a number or fact that overturns the belief |
| `troubled` | 「でも…」 objections, confusion |
| `jito` | めたん's ツッコミ at a misreading; ずんだもん's 拗ね |
| `panic` | ずんだもん overwhelmed or caught out (><) |
| `think` | a genuine question, 顎に手 |
| `angry` | a mock-angry ツッコミ; rare |
| `cry` | ずんだもん's small defeat, usually with the なみだめ voice |

めたん mostly alternates `normal` and `smile`, with `think` or `jito` now and
then. ずんだもん's face moves more. Faces the video never uses are not
embedded, so a wide range costs nothing.

## Voice styles

`style` defaults to `ノーマル`. Any talk style that `yes-speak
--list-speakers` lists for that character works, by name:

- ずんだもん: あまあま, ツンツン, セクシー, ささやき, ヒソヒソ, ヘロヘロ, なみだめ
- 四国めたん: あまあま, ツンツン, セクシー, ささやき, ヒソヒソ

Use a non-normal style for a one-line reaction or aside, about 5–8% of
lines (2–3 in a short video, 7–10 in a 12-minute one): ずんだもん なみだめ for
やられた, ヘロヘロ for exhaustion, ツンツン for 拗ね; めたん ツンツン for a
sharp ツッコミ or a ツンデレ compliment, ささやき / ヒソヒソ for
「ここだけの話」. Never on a line that explains: the odd styles are harder to
follow.

### Extra voices without art

Any other VOICEVOX character can join as a voice: an inline cast member
`{"id": "tsumugi", "speaker": "春日部つむぎ", "color": "#e0a030"}`. It speaks
with captions in its color and draws nothing, so give it a short role
(a guest expert, a phone call). Its credit is added automatically.

## Board layout

With a cast, the scene box is the board: **1072×448** inside x 104–1176,
y 48–496 of the 1280×720 stage, smaller than the single-narrator 1152×536.
The 立ち絵 cover the board's bottom corners from about y 375 down
(roughly x < 280 and x > 970). So:

- Start scenes at the top: `.scene { justify-content: flex-start; }` in the
  project's `<style>`.
- Anything that runs below about y 380 stays narrow and centred
  (`max-width` ≈ 680 px). Wide diagrams go in the upper part.
- Captions sit between the characters; never draw there or below the board.

## Credits

Never draw credits on the board. The page's 概要欄 under the player lists
every VOICEVOX character that actually spoke (`VOICEVOX:四国めたん`,
`VOICEVOX:ずんだもん`, and any extra voice) plus `立ち絵: 坂本アヒル`, built
from the cast. Write a 2–4 line `"description"` for it; `"credit"` is ignored
with a cast.

## Verify before publishing

1. `lint` clean. Errors on unknown `who`, `face` or `style` stop the build.
2. `build`; read its warnings (chars/sec, missing readings, long captions).
3. `shoot`, plus `--at start` for scenes with `data-out`. Read every PNG:
   content hidden behind a character, overflow past the board, a caption
   over a diagram, tofu (□), a build that never appears, the wrong face.
4. Listen to lines with readings, numbers or a non-normal style (`yes-speak
   'text' --speaker 四国めたん/ツンツン`). Fix readings in `readings.json`;
   only that line is re-synthesized.
5. Read `out/transcript.md` alone. Does the argument stand without the
   screen, and does each speaker sound like themselves?
