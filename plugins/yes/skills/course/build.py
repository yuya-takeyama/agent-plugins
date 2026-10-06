# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright>=1.50"]
# ///
"""Assemble a MOOC-style course page from YESUnits units built by sibling skills.

    uv run build.py build <course dir>   # build every unit via its skill, then out/course.html
    uv run build.py shoot <course dir>   # out/frames: home, every unit's first view
    uv run build.py check <course dir>   # e2e in headless Chrome: quiz, review, resume, playback

<course>/course.json:
  {"title", "subtitle", "credit", "bitrate": "32k",
   "lessons": [{"id", "title", "summary", "goals": [...],
                "units": [{"kind": "video", "src": "lessons/ai"}, {"kind": "quiz", "src": "lessons/ai/quiz.json"}]}]}
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR.parents[1] / "scripts"))
from output import export
SKILLS = SKILL_DIR.parent
# kind -> skill that knows how to build it (each exposes `build.py unit <src> --id --out`)
KINDS = {"video": "video", "quiz": "quiz", "slides": "slides"}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def load(root: Path) -> dict:
    course = json.loads((root / "course.json").read_text())
    seen = set()
    for les in course["lessons"]:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", les["id"]):
            die(f"lesson id {les['id']!r}: use lowercase letters, digits and hyphens")
        counts: dict[str, int] = {}
        for u in les["units"]:
            if u["kind"] not in KINDS:
                die(f"{les['id']}: unknown unit kind {u['kind']!r} (known: {', '.join(KINDS)})")
            counts[u["kind"]] = counts.get(u["kind"], 0) + 1
            u.setdefault("id", f"{les['id']}-{u['kind']}" + (str(counts[u["kind"]]) if counts[u["kind"]] > 1 else ""))
            if u["id"] in seen:
                die(f"unit id {u['id']!r} is used twice")
            seen.add(u["id"])
    return course


def build_unit(root: Path, u: dict, bitrate: str) -> dict:
    out = root / "out" / "units" / u["id"]
    cmd = ["uv", "run", "-q", str(SKILLS / KINDS[u["kind"]] / "build.py"), "unit", str(root / u["src"]), "--id", u["id"], "--out", str(out)]
    if u["kind"] == "video":
        cmd += ["--bitrate", bitrate]
    r = subprocess.run(cmd, text=True)
    if r.returncode != 0:
        die(f"building unit {u['id']} failed")
    return json.loads((out / "unit.json").read_text())


def cmd_build(root: Path) -> None:
    course = load(root)
    bitrate = course.get("bitrate", "32k")
    lessons, unit_data, fragments, css, js = [], {}, [], {}, {}
    n = len(course["lessons"])
    for i, les in enumerate(course["lessons"], 1):
        units = []
        for u in les["units"]:
            unit = build_unit(root, u, bitrate)
            d = unit["data"]
            if u["kind"] == "video":
                # the lesson, not the video script, names what the learner sees
                d.update(kicker=f"レッスン {i} / {n}", title=les["title"], goals=les.get("goals", d.get("goals", [])), endTitle=f"レッスン {i} 完了")
            if u["kind"] == "quiz":
                d["title"] = d.get("title") or f"確認テスト: {les['title']}"
            unit_data[u["id"]] = d
            udir = root / "out" / "units" / u["id"]
            fragments.append((udir / "unit.html").read_text())
            css.setdefault(u["kind"], (udir / "runtime.css").read_text())
            js.setdefault(u["kind"], (udir / "runtime.js").read_text())
            units.append({"id": u["id"], "kind": u["kind"], "title": unit["title"], "duration": unit.get("duration", 0), "outline": unit.get("outline", [])})
        lessons.append({"id": les["id"], "title": les["title"], "summary": les.get("summary"), "goals": les.get("goals", []), "units": units})

    # units share one page: scene ids and element ids must not collide across them
    for attr in ("data-scene", "id"):
        found: dict[str, int] = {}
        for frag in fragments:
            for v in re.findall(rf'\s{attr}="([^"]+)"', frag):
                found[v] = found.get(v, 0) + 1
        dup = sorted(k for k, c in found.items() if c > 1)
        if dup:
            die(f"duplicate {attr} across units: {', '.join(dup[:10])} — prefix them with the lesson id")

    # dialogue videos carry `credits` (every voice plus art); older units a single `credit`
    credits: list[str] = []
    for c in [course.get("credit")] + [c for d in unit_data.values() for c in d.get("credits") or [d.get("credit")]]:
        if c and c not in credits:
            credits.append(c)
    meta = {"title": course["title"], "subtitle": course.get("subtitle"), "credit": course.get("credit"), "credits": credits}
    data = json.dumps({"meta": meta, "lessons": lessons, "unitData": unit_data}, ensure_ascii=False).replace("</", "<\\/")
    page = (SKILL_DIR / "page.html").read_text()
    for key, val in {
        "__TITLE__": html.escape(course["title"]),
        "/*__SHELL_CSS__*/": (SKILL_DIR / "shell.css").read_text(),
        "/*__UNIT_CSS__*/": "\n".join(css.values()),
        "/*__UNIT_JS__*/": "\n".join(js.values()),
        "<!--__UNITS__-->": "\n".join(fragments),
        "/*__DATA__*/": data,
        "/*__SHELL_JS__*/": (SKILL_DIR / "shell.js").read_text(),
    }.items():
        if key not in page:
            die(f"page.html lost placeholder {key}")
        page = page.replace(key, val)
    out = root / "out" / "course.html"
    out.write_text(page)
    (root / "out" / "course.json").write_text(json.dumps({"lessons": lessons}, ensure_ascii=False, indent=1))
    transcripts = []
    for les in lessons:
        for u in les["units"]:
            t = root / "out" / "units" / u["id"] / "transcript.md"
            if t.exists():
                transcripts.append(f"# {les['title']}\n\n{t.read_text()}")
    (root / "out" / "transcript.md").write_text("\n\n".join(transcripts))
    total = sum(u["duration"] for les in lessons for u in les["units"])
    size = out.stat().st_size
    print(f"{len(lessons)} lessons, {total / 60:.1f} min, page {size / 1e6:.1f} MB -> {out}")


def browser():
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    # the installed Chrome: no browser download needed
    return pw, pw.chromium.launch(channel=os.environ.get("YES_BROWSER_CHANNEL", "chrome") or None, args=["--autoplay-policy=no-user-gesture-required"])


def cmd_shoot(root: Path) -> None:
    info = json.loads((root / "out" / "course.json").read_text())
    frames = root / "out" / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    url = (root / "out" / "course.html").resolve().as_uri()
    pw, b = browser()
    for name, vp in (("desktop", {"width": 1280, "height": 800}), ("mobile", {"width": 390, "height": 844})):
        page = b.new_page(viewport=vp)
        page.goto(f"{url}#home")
        page.wait_for_timeout(500)
        page.screenshot(path=str(frames / f"_home-{name}.png"))
        for les in info["lessons"]:
            for u in les["units"]:
                page.evaluate(f"location.hash = {json.dumps(u['id'])}")
                page.wait_for_timeout(500)
                page.screenshot(path=str(frames / f"{u['id']}-{name}.png"))
        page.close()
    b.close()
    pw.stop()
    print(f"-> {frames}  (scene frames come from each video's own `shoot`)")


def cmd_check(root: Path) -> None:
    """Drive the real page: answer a quiz (one wrong), review it, reload, play a video, switch lessons, resume."""
    course = load(root)
    info = json.loads((root / "out" / "course.json").read_text())
    url = (root / "out" / "course.html").resolve().as_uri()
    quiz_u = next((u for les in info["lessons"] for u in les["units"] if u["kind"] == "quiz"), None)
    video_us = [u for les in info["lessons"] for u in les["units"] if u["kind"] == "video"]
    pw, b = browser()
    page = b.new_page(viewport={"width": 1280, "height": 800})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    fails: list[str] = []

    def expect(ok: bool, what: str) -> None:
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    page.goto(f"{url}#home")
    page.wait_for_timeout(400)
    expect(page.locator(".cs-card").count() == len(info["lessons"]), "home lists every lesson")
    if quiz_u:
        src = next(u["src"] for les in course["lessons"] for u in les["units"] if u["id"] == quiz_u["id"])
        qs = json.loads((root / src).read_text())["questions"]
        page.goto(f"{url}#{quiz_u['id']}")
        page.wait_for_timeout(300)
        quiz = page.locator(f'.su-unit[data-unit="{quiz_u["id"]}"]')
        for qi, q in enumerate(qs):
            pick = (q["answer"] + 1) % len(q["choices"]) if qi == 0 else q["answer"]
            quiz.locator(".qz-q").nth(qi).locator(".qz-ch").nth(pick).click()
        expect(f"{len(qs) - 1} / {len(qs)}" in quiz.locator(".qz-result").inner_text(), "quiz scores one wrong answer")
        expect(quiz.locator(".qz-why").first.is_visible(), "quiz shows the explanation")
        page.goto(f"{url}#home")
        page.wait_for_timeout(300)
        expect("復習 (1)" in page.locator(".cs-acts").inner_text(), "home offers the review of 1 missed question")
        page.goto(f"{url}#review")
        page.wait_for_timeout(300)
        stored = page.evaluate("""({unit, answer}) => {
            document.querySelectorAll('#cs-review .qz-q .qz-ch')[answer].click();
            return JSON.parse(localStorage.getItem(`cs:${location.pathname}:u:${unit}`));
        }""", {"unit": quiz_u["id"], "answer": qs[0]["answer"]})
        expect("全問正解" in page.locator("#cs-review .qz-result").inner_text(), "review clears the missed question")
        expect(stored is not None and stored.get("wrong") == [] and stored.get("score") == len(qs) - 1,
               "review result is saved before navigation")
        page.reload()
        page.goto(f"{url}#home")
        page.wait_for_timeout(400)
        expect("復習" not in page.locator(".cs-acts").inner_text() and f"{len(qs) - 1}/{len(qs)}" in page.locator(".cs-cards").inner_text(),
               "results survive a reload")
    slides_u = next((u for les in info["lessons"] for u in les["units"] if u["kind"] == "slides"), None)
    if slides_u:
        page.goto(f"{url}#{slides_u['id']}")
        page.wait_for_timeout(500)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(300)
        expect(page.evaluate("location.hash").startswith(f"#{slides_u['id']}/"), "→ advances the deck and writes its position into the hash")
        page.keyboard.press("End")
        page.wait_for_timeout(300)
        for _ in range(40):  # walk the last slide's steps
            if page.locator(f'.su-unit[data-unit="{slides_u["id"]}"] .ss-unit-end').is_visible():
                break
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(120)
        expect(page.locator(f'.su-unit[data-unit="{slides_u["id"]}"] .ss-unit-end').is_visible(), "the deck's end offers the next step")
        page.goto(f"{url}#home")
        page.wait_for_timeout(300)
        expect("✓" in page.locator(".cs-cards").inner_text(), "finishing the deck marks it done")
    if video_us:
        v = video_us[0]
        page.goto(f"{url}#{v['id']}")
        page.wait_for_timeout(400)
        page.keyboard.press("Space")
        page.wait_for_timeout(2500)
        playing = page.evaluate("[...document.querySelectorAll('audio')].filter(a => !a.paused).map(a => a.closest('.su-unit').dataset.unit)")
        expect(playing == [v["id"]], f"space plays {v['id']} only")
        page.keyboard.press("Space")
        page.wait_for_timeout(300)
        expect(page.evaluate("location.hash").startswith(f"#{v['id']}/t="), "pausing writes the position into the hash")
        if len(video_us) > 1:
            page.locator(".cs-lesson").nth(1).locator("button").first.click()
            page.wait_for_timeout(300)
            page.keyboard.press("Space")
            page.wait_for_timeout(1500)
            playing = page.evaluate("[...document.querySelectorAll('audio')].filter(a => !a.paused).map(a => a.closest('.su-unit').dataset.unit)")
            expect(len(playing) == 1 and playing[0] != v["id"], "switching lessons stops the previous audio")
        page.locator(".cs-side-title").click()
        page.wait_for_timeout(600)
        expect(page.evaluate("location.hash") == "#home" and "続きから" in page.locator(".cs-acts").inner_text(), "home offers 続きから after watching")
    expect(not errors, f"no page errors {errors[:3]}")
    b.close()
    pw.stop()
    if fails:
        die(f"{len(fails)} check(s) failed")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "shoot", "check"])
    ap.add_argument("course", type=Path)
    ap.add_argument("--format", choices=["single", "bundle"], default="single")
    ap.add_argument("--max-bytes", type=int, help="Optional publishing-host HTML size limit")
    a = ap.parse_args()
    root = a.course.resolve()
    {"build": cmd_build, "shoot": cmd_shoot, "check": cmd_check}[a.cmd](root)
    if a.cmd == "build":
        export(root / "out" / "course.html", a.format, a.max_bytes)


if __name__ == "__main__":
    main()
