# Measuring the design skill

Run this after a change to `plugins/yes/skills/design` or to the content rules of
a format skill. It regenerates videos from a topic alone and compares them blind
with earlier versions, so the change is judged by the scripts it produces, not by
how its rules read.

## Topics

| Topic | Format | Length | Viewer |
| --- | --- | --- | --- |
| MySQL (InnoDB) のインデックスはなぜ速いのか — B+Tree の仕組み | video | 7–8 min | ソフトウェアエンジニアの大人が自習で見る |
| モンテッソーリ教育 | zundamon-video | 6–7 min | same |
| LLM Wiki（Andrej Karpathy が提案した、LLM が自分で書いて保守する Wiki に知識をためていく方式） | zundamon-video | about 10 min | same |
| TCP の輻輳制御 | video | 6–7 min | same |
| 複式簿記 | zundamon-video | 6–7 min | same |

The first three have earlier versions to compare with. The last two are held out:
judge them by the rubric alone, so a rule tuned to the first three shows whether
it generalizes.

## 1. Generate

Give each generator only the topic, format, length, viewer, the path of the
format skill in the checkout under test, and a project directory. Never give it
earlier versions, their scripts, or this file's results.

```text
Make a Japanese narrated explainer video.            (or: dialogue explainer video (ずんだもん × 四国めたん))
- Topic: <topic>
- Viewer: <viewer>
- Format: <format>, about <length>.
- Skill: follow <checkout>/plugins/yes/skills/<format>/SKILL.md and every file or
  sibling skill it tells you to read. Use the skills from that path only.
- Project dir: <dir>
- Build a single HTML file (no --format bundle).
- Research facts yourself from primary sources and list them in script.json sources.
Rules: do not read anything outside your project dir except the skill files and
your sources. Do not publish anything.
Run lint, build, shoot, check as the skills say. Reply with the files written,
the duration, the chapter and quiz counts, the checks that passed, and anything
unresolved.
```

## 2. Blind the versions

```sh
uv run evals/design/blind_compare.py prepare <round> <topic> existing=<page> v1=<page> v2=<page>
```

Each `<page>` is a built single-file video: a project's `out/video.html` or a
downloaded published page. The script writes `<round>/blind/<topic>/A.md`, `B.md`
… in one format and the mapping to `<round>/keys/<topic>.json`. Graders get the
`blind/<topic>` folder only. `uv run evals/design/blind_compare.py key <round>`
prints the mapping after grading.

## 3. Grade

One grader per topic, each reading only that topic's blind folder and
`plugins/yes/skills/design/references/rubric.md`:

```text
You are a blind reviewer comparing Japanese explainer-video scripts on the same
topic. Read ONLY <round>/blind/<topic>/*.md and the rubric. Do not guess how any
was made. `[on-screen]` is the board text of a scene; `[quiz]` lines are the
chapter-end question and its narrated answer.
1. Per version: prediction prompts before a reveal; misconceptions stated then
   refuted; quiz items that apply the idea vs recall it; quiz answers that say
   what the tempting wrong answer misses; lines that give a quiz's answer just
   before it; analogies with a stated break / total; humor lines, and how many
   sit in a mechanism or worked example, on a key line, or just before a quiz;
   whether the topic's main limit is taught.
2. Rubric pass/fail per row, with a few words for each fail.
3. Factual problems. Before calling a claim unsupported, check the script's
   sources; report it only if the source does not say it.
4. Ranking for teaching and for how pleasant it is to watch, with reasons.
```

## 4. Record

Unblind with `key`, then write one table per round: each topic's teaching rank,
watch rank, and the rows that changed. Treat one generation per version and one
grader per topic as direction, not proof; graders disagree with each other.
