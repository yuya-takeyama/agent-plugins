"""What VOICEVOX is asked to say, and the script checks that catch misreadings before synthesis.

The rules here are the single source for every YES format that speaks. Their test
cases are data (rules/cases.json) so another engine can check itself against them.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SEED = SKILL_DIR / "readings.json"

# VOICEVOX pauses 0.3-0.6 s at every space, so only spaces between two ASCII words survive
JA_SPACE = re.compile(r"(?<=[^\x00-\x7f])[ 　]+|[ 　]+(?=[^\x00-\x7f])")
ASCII_WORD = re.compile(r"[A-Za-z][A-Za-z0-9.+#'-]*")

LINE_WARN = 60  # characters on screen in one line
COMMA_WARN = 3  # 読点 in the spoken text, each a pause
CPS_WARN = 7.5  # caption characters per second of speech


def drop_ja_spaces(text: str) -> str:
    """Remove every space next to a non-ASCII character; keep only those between ASCII words."""
    return JA_SPACE.sub("", text)


def load_readings(*overlays: Path | dict | None) -> dict[str, str]:
    """The shared seed dictionary with each overlay (a readings.json path or a dict) merged over it."""
    readings = json.loads(SEED.read_text())
    for overlay in overlays:
        if isinstance(overlay, Path):
            if overlay.exists():
                readings.update(json.loads(overlay.read_text()))
        elif overlay:
            readings.update(overlay)
    return readings


def _pattern(surface: str) -> str:
    pat = re.escape(surface)
    if surface.isascii():
        # ASCII surfaces match whole words only, so "AI" never fires inside "MAIN"; a digit may come
        # before a surface that starts with a letter, so a unit reads after its number (10GB, 50ms)
        before = "A-Za-z" if surface[:1].isalpha() else "A-Za-z0-9"
        pat = rf"(?<![{before}]){pat}(?![A-Za-z0-9])"
    return pat


def apply_readings(text: str, readings: dict[str, str]) -> str:
    """Replace each surface with its reading, longest surface first."""
    for surface in sorted(readings, key=len, reverse=True):
        text = re.sub(_pattern(surface), lambda _, r=readings[surface]: r, text)
    return text


def spoken(line: dict, readings: dict[str, str]) -> str:
    """The text sent to the engine.

    `reading` is the whole line as spoken, taken as written. `say` replaces the
    caption text but still goes through the dictionary. Otherwise the caption
    `text` goes through the dictionary. Spaces next to Japanese are dropped last."""
    if line.get("reading"):
        return drop_ja_spaces(line["reading"])
    return drop_ja_spaces(apply_readings(line.get("say") or line["text"], readings))


# ---------- checks ----------

def length_warning(line: dict) -> str | None:
    n = len(line["text"])
    return f"{line['id']}: {n} chars (> {LINE_WARN}); split the sentence" if n > LINE_WARN else None


def comma_warning(line: dict, said: str) -> str | None:
    commas = said.count("、")
    if commas >= COMMA_WARN:
        return f"{line['id']}: {commas} 読点, each a pause in speech; join a list with と or split the sentence"
    return None


def unread_words(said: str) -> list[str]:
    return sorted({w for w in ASCII_WORD.findall(said) if len(w) > 1})


def unread_warning(line: dict, said: str) -> str | None:
    if line.get("reading"):
        return None
    left = unread_words(said)
    if left:
        return f"{line['id']}: no reading for {', '.join(left)} — add to readings.json or give the line a reading"
    return None


def cps_warning(line: dict, seconds: float) -> str | None:
    cps = len(line["text"]) / max(seconds, 0.1)
    return f"{line['id']}: {cps:.1f} chars/s on screen (> {CPS_WARN})" if cps > CPS_WARN else None


def line_warnings(line: dict, readings: dict[str, str], seconds: float | None = None) -> list[str]:
    """Length, 読点, unread English and (with the measured length) caption speed for one line."""
    said = spoken(line, readings)
    found = [length_warning(line), comma_warning(line, said), unread_warning(line, said)]
    if seconds is not None:
        found.append(cps_warning(line, seconds))
    return [w for w in found if w]


def space_warnings(lines: list[dict], readings: dict[str, str]) -> list[str]:
    """Spaces the build will drop. They never become pauses, so write the reading joined
    (トゥルータイム, not トゥルー タイム) and use 、 or a line's pause where a breath is wanted."""
    out = []
    for surface, value in readings.items():
        if JA_SPACE.search(value):
            out.append(f"readings[{surface!r}] = {value!r}: spaces next to Japanese are dropped, not paused; "
                       f"write {drop_ja_spaces(value)!r}")
    for line in lines:
        for key in ("reading", "say"):
            if line.get(key) and JA_SPACE.search(line[key]):
                out.append(f"{line['id']}: {key} has spaces next to Japanese; they are dropped, not paused — "
                           "use 、 or the line's pause for a break")
    return out


# Patterns VOICEVOX reads other than intended. Measured against VOICEVOX 0.25.2 (ずんだもん): each
# rewrite changed the synthesized length, while 12000円 = 1万2000円 and 11/22 = 11月22日 did not.
# Not errors: lines to listen to, or to rewrite.
NUMBER_HINTS = (
    (re.compile(r"\d+\.\d+\.\d+"), "version number: listen, or give the line a reading (バージョンにてんいち)"),
    (re.compile(r"\d+\s*[〜~～]\s*\d+"), "range with 〜: write 3から5"),
    (re.compile(r"(?<![\d/])\d{1,2}/\d{1,2}(?![\d/])"), "a/b is read like a date (11/22 sounds like 11月22日): write 3分の1 for a fraction"),
    (re.compile(r"\d{1,2}:\d{2}"), "clock time with a colon: write 10時30分"),
    (re.compile(r"\d+\s*[xX×]\s*\d+|\d+[xX×](?![A-Za-z])"), "x for times: write 3倍 or 1920かける1080"),
)


def number_hints(text: str) -> list[str]:
    return [note for pat, note in NUMBER_HINTS if pat.search(text)]
