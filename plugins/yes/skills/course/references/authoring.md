All commands and relative resource paths below are relative to the owning skill directory, one level above this reference. `<PLUGIN>` is the directory containing `plugin.json`.

# course

A course is a dir with `course.json` that lists lessons; each lesson is a
sequence of **units**, and each unit is built by the skill that owns its
kind. This skill owns the shell (outline, home, progress, review) and the
orchestration; it never renders a video or a question itself.

| kind    | skill                   | source            |
|---------|-------------------------|-------------------|
| `video` | `video` | a video project dir (`script.json` + `scenes.html`) |
| `quiz`  | `quiz`            | a `quiz.json`     |
| `slides`| `slides`          | a deck `.html` made from its template |

```json
{
  "title": "Cloudflare 2026年9月のアップデート講座",
  "subtitle": "…", "credit": "VOICEVOX:ずんだもん", "bitrate": "32k",
  "lessons": [
    {"id": "ai", "title": "AI とエージェント", "summary": "…", "goals": ["…を説明できる"],
     "units": [{"kind": "video", "src": "lessons/ai"}, {"kind": "quiz", "src": "lessons/ai/quiz.json"}]}
  ]
}
```

```sh
S='/absolute/path/to/plugin/skills/course'
uv run $S/build.py build <course>   # builds every unit via its skill (TTS cached) -> out/course.html
uv run $S/build.py shoot <course>   # out/frames: home + every unit, desktop and mobile; LOOK at them
uv run $S/build.py check <course>   # e2e in headless Chrome; every line must say ok
```

Unit ids default to `<lesson>-<kind>` (`ai-video`, `ai-quiz`). The lesson's
`title` and `goals` replace the video's own on its start screen.

## Orchestration

1. **Split the topic.** From the sources, choose 4–8 lessons of 3–5 minutes,
   each owning a distinct part of the topic. Write the lesson list with one
   line of scope each, and decide which lesson owns any item two sources both
   mention. No "overview" lesson that previews the others — the home view
   already shows the course; an intro lesson only if it teaches something
   none of the others do.
2. **Write each lesson.** Use `lesson-brief.md` to capture the learner, sources,
   scope, and input/output paths. Work sequentially unless the user and host
   allow subagents. No specific model or agent tool is required.
3. **Review the drafts as the editor** — this is where quality comes from:
   - overlap: list every item and the lessons that teach it (read each
     `script.json`); keep each in one lesson and send the others back.
   - meta: grep narration, scenes and questions for course structure,
     announcement framing and dates (`発表|Birthday|changelog|9月の|どのレッスン`).
     Send back anything found.
   - tests: each question asks about substance (要件→選択, なぜ, 気をつける点).
   - unit choice: narrated video for a mechanism or a story that unfolds;
     slides for reference material the learner steps through at their own
     pace (tables, comparisons, code); quiz after each lesson.
   Revise the affected lessons until clean.
4. **Write course.json** from the writers' reports (summary, goals) and build.
5. **Verify**: `shoot` (home, each unit, desktop + mobile) and read the
   frames; `check` must pass; skim `out/transcript.md` for overlap once more.
6. **Deliver** `out/course.html`, or its bundle, with verification results.

## Page behavior (runtime, do not re-implement)

- Home: progress, 続きから (last paused unit and position), lesson cards with
  each unit's status, 間違えた問題を復習 when any question is still missed.
- Outline: lessons with their duration; the current lesson expands into its
  video chapters and its test with the score badge. On narrow screens it is
  a drawer behind ☰ 目次.
- Nothing is locked. A video unit is done once 85 % of it was actually
  played (seeking does not count); a slides unit once its last step was
  reached; a quiz unit once it was taken; a lesson once all its units are done. A video's end screen leads to the next unit
  (確認テストへ) or lesson; a quiz's leads to the next lesson or back to the video.
- Review: one quiz over every missed question, labelled with its lesson;
  answering one right removes it from the missed list (the lesson's score
  stays as first taken).
- State is saved to localStorage where available and otherwise kept in memory.
  Sandboxed viewers may disable persistence; the course still works.
- Deep links: `#home`, `#review`, `#<lesson>` (its first unfinished unit),
  `#<unit>[/<rest>]` where rest is the unit's own (`t=12.3`, a chapter id).

## Adding a unit kind

A kind is a skill whose `build.py unit <src> --id ID --out DIR` writes
`unit.json` (`id, kind, title, duration?, outline: [{rest, title}], data`),
`unit.html` (`<div class="su-unit" data-unit=ID data-kind=KIND hidden>…</div>`),
`runtime.js` (registers `YESUnits.kinds.KIND`, contract in
`video/runtime.js`) and `runtime.css`. Then add it to
`KINDS` in `build.py`.
