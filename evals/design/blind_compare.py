# /// script
# requires-python = ">=3.11"
# ///
"""Turn built yes video pages into blind, same-format scripts for a reviewer.

    md PAGE OUT.md                       one page -> narration markdown
    prepare ROUND TOPIC NAME=PAGE ...    shuffle versions into ROUND/blind/TOPIC/{A,B,C}.md
    key ROUND                            print which letter is which version

PAGE is a built single-file video (out/video.html or a downloaded published page).
Every version goes through the same extractor, so formatting cannot reveal its origin.
"""
from __future__ import annotations

import hashlib
import html
import json
import random
import re
import sys
from pathlib import Path

LETTERS = "ABCDEFGH"


def page_data(page: str) -> dict:
    i = page.find("const DATA = ")
    if i < 0:
        raise SystemExit("not a yes video page: no `const DATA = ` in it")
    data, _ = json.JSONDecoder().raw_decode(page, i + len("const DATA = "))
    return data["data"]


def boards(page: str) -> dict[str, str]:
    out = {}
    for m in re.finditer(r'<section[^>]*data-scene="([^"]+)"[^>]*>(.*?)</section>', page, re.S):
        body = re.sub(r"<(style|script)\b.*?</\1>", "", m.group(2), flags=re.S)
        out[m.group(1)] = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))).strip()[:350]
    return out


def to_markdown(page: str) -> str:
    data, board = page_data(page), boards(page)
    tl = data["timeline"]
    titles = {c["id"]: c.get("title", "") for c in tl["chapters"]}
    chars = sum(len(ln["text"]) for ln in tl["lines"] if not ln["scene"].endswith("-quiz"))
    quizzes = sum(1 for s in tl["scenes"] if s["id"].endswith("-quiz"))
    out = [f"# {data.get('title', '')}", "goals:", *[f"- {g}" for g in data.get("goals", [])],
           f"duration_sec: {round(tl['duration'])}", f"narration_chars: {chars}",
           f"chapters: {len(tl['chapters'])}; quiz items: {quizzes}"]
    chapter = scene = None
    for ln in tl["lines"]:
        if ln["chapter"] != chapter:
            chapter = ln["chapter"]
            out.append(f"\n## Chapter {chapter}: {titles.get(chapter, '')}")
        who = f"{ln['who']}: " if ln.get("who") else ""
        if ln["scene"].endswith("-quiz"):
            scene = ln["scene"]
            out.append(f"[quiz] {who}{ln['text']}")
            continue
        if ln["scene"] != scene:
            scene = ln["scene"]
            out.append(f"\n### scene {scene}")
            if board.get(scene):
                out.append(f"[on-screen] {board[scene]}")
        out.append(f"{who}{ln['text']}")
    return "\n".join(out) + "\n"


def prepare(round_dir: Path, topic: str, versions: dict[str, Path]) -> dict[str, str]:
    names = sorted(versions)
    seed = int(hashlib.sha256(f"{round_dir.name}/{topic}".encode()).hexdigest(), 16)
    random.Random(seed).shuffle(names)
    blind = round_dir / "blind" / topic
    blind.mkdir(parents=True, exist_ok=True)
    key = {}
    for letter, name in zip(LETTERS, names):
        (blind / f"{letter}.md").write_text(to_markdown(versions[name].read_text()))
        key[letter] = name
    keys = round_dir / "keys"
    keys.mkdir(parents=True, exist_ok=True)
    (keys / f"{topic}.json").write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n")
    return key


def main(argv: list[str]) -> None:
    if len(argv) >= 3 and argv[0] == "md":
        Path(argv[2]).write_text(to_markdown(Path(argv[1]).read_text()))
    elif len(argv) >= 4 and argv[0] == "prepare":
        versions = dict(arg.split("=", 1) for arg in argv[3:])
        if len(versions) > len(LETTERS):
            raise SystemExit(f"at most {len(LETTERS)} versions")
        key = prepare(Path(argv[1]), argv[2], {k: Path(v) for k, v in versions.items()})
        print(f"{argv[1]}/blind/{argv[2]}: " + " ".join(sorted(key)))
    elif len(argv) == 2 and argv[0] == "key":
        for path in sorted((Path(argv[1]) / "keys").glob("*.json")):
            key = json.loads(path.read_text())
            print(f"{path.stem}: " + " ".join(f"{k}={v}" for k, v in sorted(key.items())))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
