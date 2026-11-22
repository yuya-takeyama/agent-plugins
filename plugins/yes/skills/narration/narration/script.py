"""A narration script as an ordered list of lines, each with its speaker and the pause after it.

    {"title", "speed"?, "cast"?, "pauses"?, "readings"?, "bgm"?,
     "chapters": [{"id", "title", "scenes": [{"id", "lines": [...]}]}   # or "lines" right in the chapter
                  , "quiz"?: {"q", "a", "think"?, "q_who"?, "a_who"?}]}

A line is a string or {text, reading?, say?, who?, style?, pause?}. The video skills use the same
shape (their scenes.html adds the picture), so one script can be heard, linted and built as either.
"""
from __future__ import annotations

from . import die

# The pause after a line, by what comes next (seconds). The video player uses these as they are.
PAUSES = {
    "line": 0.35,     # the next line, same speaker
    "turn": None,     # the next line, another speaker (None: same as line)
    "scene": 0.9,     # after a scene's last line
    "chapter": 1.4,   # after a chapter's last line
    "end": 1.0,       # after the very last line
    "think": 4.0,     # a quiz question's thinking time
    "lead_in": 0.4,   # silence before the first line
}
DEFAULT_STYLE = "ノーマル"
# The voices YES supports, by the short ids the video skills' characters use.
VOICE_IDS = {"zundamon": "ずんだもん", "metan": "四国めたん"}


def pauses_for(script: dict) -> dict:
    custom = script.get("pauses") or {}
    if not isinstance(custom, dict) or any(k not in PAUSES for k in custom):
        die(f"pauses: an object with any of {', '.join(PAUSES)}")
    for k, v in custom.items():
        if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 10):
            die(f"pauses.{k}: seconds between 0 and 10")
    return {**PAUSES, **custom}


def load_cast(script: dict) -> list[dict]:
    """[{id, name, speaker, color?}] from "cast": ids such as "zundamon", or inline {id, speaker, name?, color?}."""
    cast = []
    for raw in script.get("cast", []):
        if isinstance(raw, str):
            speaker = VOICE_IDS.get(raw, raw)
            cast.append({"id": raw, "name": speaker, "speaker": speaker})
        elif isinstance(raw, dict) and raw.get("id") and raw.get("speaker"):
            cast.append({"id": raw["id"], "name": raw.get("name", raw["speaker"]), "speaker": raw["speaker"],
                         **({"color": raw["color"]} if raw.get("color") else {})})
        else:
            die(f"cast member needs id and speaker: {raw!r}")
    return cast


def norm_line(raw) -> dict:
    line = {"text": raw} if isinstance(raw, str) else dict(raw)
    if not line.get("text"):
        die(f"line without text: {raw!r}")
    return line


def flatten(script: dict, cast: list[str] | None = None, pauses: dict | None = None,
            carry: tuple[str, ...] = ()) -> list[dict]:
    """Every spoken line in order, with its scene/chapter and the pause after it.

    With a cast (ids), each line also gets `who` (default: the previous line's speaker, first the first
    member) and `style` (default ノーマル). `carry` copies more line fields (the video's `face`)."""
    p = pauses or PAUSES
    out: list[dict] = []
    explainer = cast[0] if cast else None
    who = explainer
    chapters = script["chapters"]
    for ci, ch in enumerate(chapters):
        scenes = list(ch["scenes"]) if "scenes" in ch else [{"id": ch["id"], "lines": ch.get("lines", [])}]
        if ch.get("quiz"):
            q = ch["quiz"]
            scenes.append({
                "id": f"{ch['id']}-quiz", "kind": "quiz",
                "lines": [
                    {"text": q["q"], "reading": q.get("q_reading"), "pause": q.get("think", p["think"]),
                     "who": q.get("q_who") or explainer},
                    {"text": q["a"], "reading": q.get("a_reading"), "who": q.get("a_who") or explainer},
                ],
            })
        for si, sc in enumerate(scenes):
            lines = [norm_line(ln) for ln in sc["lines"]]
            for li, line in enumerate(lines):
                last_in_scene = li == len(lines) - 1
                last_in_ch = last_in_scene and si == len(scenes) - 1
                default = p["chapter"] if last_in_ch else p["scene"] if last_in_scene else p["line"]
                if ci == len(chapters) - 1 and last_in_ch:
                    default = p["end"]
                entry = {
                    "id": f"{sc['id']}.{li}", "chapter": ch["id"], "scene": sc["id"],
                    "kind": sc.get("kind", "scene"), "idx": li,
                    "role": sc.get("role"), "aside": bool(line.get("aside")),
                    "text": line["text"], "reading": line.get("reading"),
                    "pause": float(line.get("pause") if line.get("pause") is not None else default),
                }
                if line.get("say"):
                    entry["say"] = line["say"]
                if cast:
                    who = line.get("who") or who
                    entry.update(who=who, style=line.get("style") or DEFAULT_STYLE)
                for key in carry:
                    if key in line:
                        entry[key] = line[key]
                # a turn pause applies only where the script left the pause to the default
                entry["_turn"] = line.get("pause") is None and not last_in_scene
                out.append(entry)
    for a, b in zip(out, out[1:]):
        if a.pop("_turn") and p.get("turn") is not None and a.get("who") != b.get("who"):
            a["pause"] = float(p["turn"])
    if out:
        out[-1].pop("_turn", None)
    return out


def check_cast(lines: list[dict], cast: list[dict], styles: dict | None) -> list[str]:
    """Unknown who or style. `styles` None skips the style check (speaker list unavailable)."""
    by_id = {m["id"]: m for m in cast}
    errs = []
    for ln in lines:
        m = by_id.get(ln["who"])
        if not m:
            errs.append(f"{ln['id']}: unknown who {ln['who']!r} (cast: {', '.join(by_id)})")
            continue
        if styles is not None and (m["speaker"], ln["style"]) not in styles:
            known = [s for sp, s in styles if sp == m["speaker"]]
            errs.append(f"{ln['id']}: {m['speaker']} has no style {ln['style']!r}"
                        + (f" (styles: {', '.join(known)})" if known else " (speaker not in --list-speakers)"))
    return errs


def chapter_spans(script: dict, timed: list[dict], duration: float) -> list[dict]:
    """[{id, title, start, end}] from the timed lines."""
    chapters: list[dict] = []
    for ln in timed:
        if not chapters or chapters[-1]["id"] != ln["chapter"]:
            ch = next(c for c in script["chapters"] if c["id"] == ln["chapter"])
            chapters.append({"id": ch["id"], "title": ch.get("title", ch["id"]), "start": ln["start"]})
    for a, b in zip(chapters, chapters[1:] + [None]):
        a["end"] = b["start"] if b else duration
    return chapters
