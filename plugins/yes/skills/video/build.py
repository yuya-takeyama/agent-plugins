# /// script
# requires-python = ">=3.11"
# dependencies = ["budoux>=0.6", "imageio-ffmpeg>=0.5", "playwright>=1.50", "fonttools>=4.50", "brotli>=1.1"]
# ///
"""Build a narrated explainer video: a standalone HTML page, or a YESUnits unit for a course.

    uv run build.py lint  <project>   # script checks only, no synthesis
    uv run build.py build <project>   # synth (cached) -> timeline -> captions -> out/video.html
    uv run build.py shoot <project> [--at end|start|mid] [--only s3,s4]
    uv run build.py check <project>   # e2e in headless Chrome on out/video.html: maximize (F / button / Esc, fallback)
    uv run build.py unit  <project> --id ID --out DIR [--bitrate 32k]   # unit bundle for course
    uv run build.py tts-plan <project>  # out/tts-plan.json: the sentences YES_TTS_FILES still needs as WAV files

<project>/script.json   narration, chapters, scenes, quizzes (see SKILL.md)
<project>/scenes.html   one <section class="scene" data-scene="ID"> per non-quiz scene
<project>/readings.json optional {"surface": "reading"} merged over the narration skill's readings.json

Readings, script checks, speech sources, synthesis and the audio track come from the sibling
narration skill (../narration/narration/); its references/engines.md lists the speech sources
(the bundled `yes-speak`, YES_VOICEVOX_URL, YES_TTS_CMD, YES_TTS_FILES).
"""

from __future__ import annotations

import argparse
import base64
import math
import os
import hashlib
import html
import json
import io
import re
import shutil
import sys
import urllib.request
from urllib.parse import urlsplit
from pathlib import Path

import budoux

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR.parents[1] / "scripts"))
sys.path.insert(0, str(SKILL_DIR.parent / "narration"))
from markup import attr_values
from output import export
from voice_licenses import SUPPORTED_VOICES, usage_notice, voice_policy
from narration import audio, manifest, voices
from narration import reading as rd
from narration import script as sc
from narration.voices import licensed, list_speakers, style_ids, synth
from narration.audio import RATE, encode

CAPTION_MAX = 40  # chars per cue (two lines of ~20)
DEICTIC = re.compile(r"この図|この部分|ここを|ここで見|こちら|この赤|この青|これを見")
reading_of = rd.spoken
CHARACTERS = SKILL_DIR / "characters"
DEFAULT_FACE = "normal"
MOUTH_FPS = 30
MOUTH_FLOOR = 300  # RMS below this (about -40 dBFS) is silence, whatever the line's loudness
MOUTH_UP = (0.2, 0.5)  # normalized RMS that opens the mouth to half / open
MOUTH_DOWN = (0.12, 0.38)  # and the lower levels it must fall below to close again

parser_ja = budoux.load_default_japanese_parser()


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------- script model ----------

def load_project(root: Path) -> tuple[dict, dict, list[dict], list[dict]]:
    script = json.loads((root / "script.json").read_text())
    readings = rd.load_readings(root / "readings.json", script.get("readings"))
    cast = load_cast(script)
    KEEP_WHOLE.update(w for w in [*readings, *(m["name"] for m in cast)] if len(w) > 1)
    return script, readings, cast, flatten(script, [m["id"] for m in cast])


def load_cast(script: dict) -> list[dict]:
    """The script's cast in order. A member with art keeps its characters/<id>.json as `char`."""
    cast = []
    for raw in script.get("cast", []):
        if isinstance(raw, str):
            path = CHARACTERS / f"{raw}.json"
            if not path.exists():
                die(f"cast member {raw!r}: no {path}; write it inline as {{\"id\", \"speaker\"}} for a voice without art")
            char = json.loads(path.read_text())
            cast.append({"id": raw, "name": char["name"], "speaker": char["speaker"], "color": char.get("color"), "char": char})
        else:
            if not (raw.get("id") and raw.get("speaker")):
                die(f"inline cast member needs id and speaker: {raw!r}")
            cast.append({"id": raw["id"], "name": raw.get("name", raw["speaker"]), "speaker": raw["speaker"], "color": raw.get("color")})
    if licensed():
        for member in cast:
            if member["speaker"] not in SUPPORTED_VOICES:
                die("YES supports only ずんだもん and 四国めたん as VOICEVOX voices in the cast.")
    return cast


def flatten(script: dict, cast: list[str] | None = None) -> list[dict]:
    """Every narrated line in order, with its scene/chapter and the pause after it (narration's script).

    With a cast (ids), each line also gets `who` (default: the previous line's speaker),
    `style` (default ノーマル) and `face` (sticky per character)."""
    lines = sc.flatten(script, cast, carry=("face",))
    faces: dict[str, str] = {}
    for ln in lines:
        face = ln.pop("face", None)
        if cast:
            faces[ln["who"]] = face or faces.get(ln["who"], DEFAULT_FACE)
            ln["face"] = faces[ln["who"]]
    return lines


# ---------- lint ----------

OPEN_TAG = re.compile(r"<[A-Za-z][^<>]*>")


def out_implies_at(scenes_html: str) -> str:
    """The runtime only schedules [data-at] elements, so a lone data-out would never hide."""
    def fix(m: re.Match) -> str:
        tag = m.group(0)
        if re.search(r"\sdata-out=", tag) and not re.search(r"\sdata-at=", tag):
            return re.sub(r"\sdata-out=", ' data-at="0" data-out=', tag, count=1)
        return tag
    return OPEN_TAG.sub(fix, scenes_html)


QUIZ_ECHO_WARN = 0.35


def lint(lines: list[dict], readings: dict, durations: dict | None = None) -> list[str]:
    """The narration skill's line checks (length, 読点, unread English, caption speed) plus the video's own."""
    warns = []
    for ln in lines:
        t = ln["text"]
        said = rd.spoken(ln, readings)
        warns += [w for w in (rd.length_warning(ln), rd.comma_warning(ln, said)) if w]
        if DEICTIC.search(t):
            warns.append(f"{ln['id']}: deictic phrase '{DEICTIC.search(t).group()}' — name the thing so audio-only works")
        if w := rd.unread_warning(ln, said):
            warns.append(w)
        if durations and ln["id"] in durations and (w := rd.cps_warning(ln, durations[ln["id"]])):
            warns.append(w)
        # the dialogue layout has room for two caption lines between the characters
        if "who" in ln and len(caption_chunks(t)) > 2:
            warns.append(f"{ln['id']}: caption runs over 2 lines; split the sentence")
    warns += quiz_echo_warnings(lines)
    warns += placement_warnings(lines)
    return warns


ROLES = ("hook", "example", "mechanism", "transition", "close")
NO_ASIDE_BEFORE_QUIZ = 3


def placement_warnings(lines: list[dict]) -> list[str]:
    """Every scene names its role; humor (`aside`) stays out of examples, mechanisms and quiz lead-ins."""
    warns, seen = [], set()
    for i, ln in enumerate(lines):
        scene = ln.get("scene")
        if not scene or scene.endswith("-quiz"):
            continue
        if scene not in seen:
            seen.add(scene)
            if ln.get("role") not in ROLES:
                warns.append(f"{scene}: role must be one of {', '.join(ROLES)}")
        if not ln.get("aside"):
            continue
        if ln.get("role") in ("example", "mechanism"):
            warns.append(f"{ln['id']}: humor in a {ln['role']} scene; cut it")
        ahead = lines[i + 1:i + 1 + NO_ASIDE_BEFORE_QUIZ]
        if any(x.get("scene", "").endswith("-quiz") for x in ahead):
            warns.append(f"{ln['id']}: humor right before a quiz; cut it")
    return warns


def _bigrams(text: str) -> set[str]:
    t = re.sub(r"[\s、。！？!?「」（）()・,.:：…]", "", text)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def quiz_echo_warnings(lines: list[dict]) -> list[str]:
    """A quiz answer already spoken in the lines just before the question is an echo, not recall."""
    warns = []
    for i, ln in enumerate(lines):
        if not ln.get("scene", "").endswith("-quiz") or i == 0 or lines[i - 1].get("scene") != ln.get("scene"):
            continue
        before = [x["text"] for x in lines[max(0, i - 4):i - 1] if x.get("chapter") == ln.get("chapter")]
        answer = _bigrams(ln["text"])
        if answer and len(answer & _bigrams(" ".join(before))) / len(answer) >= QUIZ_ECHO_WARN:
            warns.append(f"{ln['id']}: the quiz answer repeats the lines just before the question; "
                         "end the chapter on something the answer does not restate")
    return warns


def source_errors(sources: object) -> list[str]:
    """Reject malformed references before starting speech synthesis."""
    if not isinstance(sources, list):
        return ['sources: must be a list of {"title", "url"}']
    errs = []
    for i, source in enumerate(sources):
        if not isinstance(source, dict) or not isinstance(source.get("title"), str) or not source["title"].strip():
            errs.append(f"sources[{i}]: needs a nonempty title")
            continue
        url = source.get("url")
        try:
            parsed = urlsplit(url) if isinstance(url, str) else None
            valid = parsed is not None and parsed.scheme in ("http", "https") and bool(parsed.hostname)
        except ValueError:
            valid = False
        if not valid:
            errs.append(f"sources[{i}]: url must be an absolute http(s) URL")
        if "note" in source and not isinstance(source["note"], str):
            errs.append(f"sources[{i}]: note must be a string")
    return errs


DIGIT = re.compile(r"[0-9０-９]")


def claim_errors(script: dict, lines: list[dict]) -> list[str]:
    """Malformed claims ledger entries: each names a line and exactly one of quote, derived, fiction."""
    claims = script.get("claims", [])
    if not isinstance(claims, list):
        return ["claims: must be a list"]
    ids, n_sources = {ln["id"] for ln in lines}, len(script.get("sources") or [])
    errs = []
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict) or claim.get("line") not in ids:
            errs.append(f"claims[{i}]: line must be a narrated line id such as c1-1.0")
            continue
        kinds = [k for k in ("quote", "derived", "fiction") if k in claim]
        if len(kinds) != 1:
            errs.append(f"claims[{i}]: give exactly one of quote (with source), derived or fiction")
        elif kinds == ["quote"]:
            if not isinstance(claim["quote"], str) or not claim["quote"].strip():
                errs.append(f"claims[{i}]: quote must be the source's own words")
            source = claim.get("source")
            if not isinstance(source, int) or isinstance(source, bool) or not 0 <= source < n_sources:
                errs.append(f"claims[{i}]: source must be an index into sources")
        elif kinds == ["derived"] and claim["derived"] not in ids:
            errs.append(f"claims[{i}]: derived must name the line it restates or computes from")
        elif kinds == ["fiction"] and claim["fiction"] is not True:
            errs.append(f"claims[{i}]: fiction must be true")
    return errs


def assumes_errors(script: dict) -> list[str]:
    assumes = script.get("assumes", [])
    if not isinstance(assumes, list) or not all(isinstance(a, str) and a.strip() for a in assumes):
        return ["assumes: must be a list of nonempty strings"]
    return []


def assumes_warnings(script: dict) -> list[str]:
    return [] if script.get("assumes") else [
        'assumes: list what the viewer must already know (the brief\'s Learner), shown under 前提 in the description']


def claim_warnings(script: dict, lines: list[dict]) -> list[str]:
    """A line with a number and no ledger entry is a factual claim nobody tied to a source."""
    declared = {c.get("line") for c in script.get("claims", []) if isinstance(c, dict)}
    return [f"{ln['id']}: has a number but no claims entry; quote its source, or mark it derived or fiction"
            for ln in lines if DIGIT.search(ln["text"]) and ln["id"] not in declared]


def cast_errors(lines: list[dict], cast: list[dict], styles: dict | None) -> list[str]:
    """Unknown who / face / style. `styles` None skips the style check (speaker list unavailable)."""
    by_id = {m["id"]: m for m in cast}
    errs = []
    for ln in lines:
        m = by_id.get(ln["who"])
        if not m:
            errs.append(f"{ln['id']}: unknown who {ln['who']!r} (cast: {', '.join(by_id)})")
            continue
        if "char" in m and ln["face"] not in m["char"]["faces"]:
            errs.append(f"{ln['id']}: {m['id']} has no face {ln['face']!r} (faces: {', '.join(m['char']['faces'])})")
        if styles is not None and (m["speaker"], ln["style"]) not in styles:
            known = [s for sp, s in styles if sp == m["speaker"]]
            errs.append(f"{ln['id']}: {m['speaker']} has no style {ln['style']!r}"
                        + (f" (styles: {', '.join(known)})" if known else " (speaker not in --list-speakers)"))
    return errs


# ---------- voices ----------

def credits_for(timed: list[dict], cast: list[dict], speakers: list[dict]) -> list[str]:
    """Each voiced character's credit in order of first appearance, then each art source once."""
    speaker_of = {m["id"]: m["speaker"] for m in cast}
    credit_of = {sp["name"]: sp.get("credit") or f"VOICEVOX:{sp['name']}" for sp in speakers}
    out: list[str] = []
    for c in [credit_of[speaker_of[ln["who"]]] for ln in timed] + [
            m["char"].get("source", {}).get("credit") for m in cast if "char" in m]:
        if c and c not in out:
            out.append(c)
    return out


def narration_credit(script: dict) -> str:
    credit = script.get("credit")
    if isinstance(credit, str) and credit.strip():
        return credit.strip()
    if not licensed():
        die('A single-narrator script with YES_TTS_ENGINE=other needs a nonempty "credit".')
    return "VOICEVOX:ずんだもん"


def terms_for(script: dict, cast: list[dict], lines: list[dict], speakers: list[dict]) -> dict:
    art = [m["char"].get("source", {}) for m in cast if "char" in m]
    if not licensed():
        terms = script.get("usageTerms", usage_notice([], art) if art else {})
    else:
        used = {m["speaker"] for m in cast if any(ln["who"] == m["id"] for ln in lines)}
        voiced = [sp for sp in speakers if sp["name"] in used] if cast else [
            {"name": "ずんだもん", **voice_policy("ずんだもん")}]
        # only the bundled engine's version is known; another VOICEVOX gets the current terms
        terms = usage_notice(voiced, art, pinned=voices.pinned())
    if not isinstance(terms, dict) or not isinstance(terms.get("text", ""), str):
        die("usageTerms must be an object with text and optional links.")
    if terms and not terms.get("text", "").strip():
        die("usageTerms.text must not be empty.")
    if errs := source_errors(terms.get("links", [])):
        die("usageTerms: " + "\n".join(errs))
    return terms


# ---------- caption font ----------

# The dialogue captions carry a thick outline; an angular fallback face spikes at its corners, so the
# rounded face the captions are designed for is embedded, cut down to the characters the captions use.
CAPTION_FONT = {
    "family": "M PLUS Rounded 1c",
    "url": "https://raw.githubusercontent.com/google/fonts/7d1c962b6fbc8987b59ed229bbe5c12764d3a624/ofl/mplusrounded1c/MPLUSRounded1c-ExtraBold.ttf",
    "sha256": "8e7c15901dca87f1451b356dda594f7d092ba252a5dcc47da74523a242493c36",
}
FONT_CACHE = Path(os.environ.get("YES_FONT_CACHE", Path.home() / ".cache" / "yes" / "fonts"))


def caption_font_file() -> Path | None:
    path = FONT_CACHE / Path(CAPTION_FONT["url"]).name
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != CAPTION_FONT["sha256"]:
        path.unlink()
    if not path.exists():
        try:
            FONT_CACHE.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(CAPTION_FONT["url"], timeout=60) as r:
                body = r.read()
        except OSError as e:
            print(f"warn: caption font download failed ({e}); captions use the system font")
            return None
        if hashlib.sha256(body).hexdigest() != CAPTION_FONT["sha256"]:
            print("warn: caption font checksum mismatch; captions use the system font")
            return None
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(body)
        os.replace(tmp, path)
    return path


def caption_font_css(texts: list[str], family: str) -> str:
    """An @font-face for `family` holding only the glyphs of `texts`, as WOFF2 in a data: URI ('' without the font)."""
    src = caption_font_file()
    if src is None:
        return ""
    from fontTools import subset

    chars = "".join(sorted(set("".join(texts)) | set("…ー。、！？「」（）")))
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    font = subset.load_font(str(src), opts)
    sub = subset.Subsetter(opts)
    sub.populate(text=chars)
    sub.subset(font)
    buf = io.BytesIO()
    subset.save_font(font, buf, opts)
    data = base64.b64encode(buf.getvalue()).decode()
    return (f'@font-face{{font-family:"{family}";font-weight:800;font-display:block;'
            f'src:url(data:font/woff2;base64,{data}) format("woff2")}}')


# ---------- lip sync ----------

def mouth_levels(pcm: bytes) -> list[int]:
    """Per 1/MOUTH_FPS s frame: 0 closed, 1 half, 2 open, from RMS normalized to the line."""
    samples = audio.samples(pcm)
    step = RATE // MOUTH_FPS
    rms = []
    for i in range(0, len(samples), step):
        frame = samples[i:i + step]
        rms.append(math.sqrt(sum(s * s for s in frame) / len(frame)))
    voiced = sorted(r for r in rms if r >= MOUTH_FLOOR)
    # the 90th percentile, so one loud syllable doesn't leave the rest half-closed
    ref = voiced[int(len(voiced) * 0.9)] if voiced else 1.0
    levels, level = [], 0
    for r in rms:
        x = min(r / ref, 1.0) if r >= MOUTH_FLOOR else 0.0
        up = 2 if x >= MOUTH_UP[1] else 1 if x >= MOUTH_UP[0] else 0
        down = 2 if x >= MOUTH_DOWN[1] else 1 if x >= MOUTH_DOWN[0] else 0
        level = up if up > level else down if down < level else level
        levels.append(level)
    return drop_blips(levels)


def drop_blips(levels: list[int]) -> list[int]:
    """Merge every one-frame run into its neighbour (the previous run, or the next at the start)."""
    runs: list[list[int]] = []
    for v in levels:
        if runs and runs[-1][0] == v:
            runs[-1][1] += 1
        else:
            runs.append([v, 1])
    merged: list[list[int]] = []
    for i, (v, n) in enumerate(runs):
        if n == 1 and len(runs) > 1:
            v = merged[-1][0] if merged else runs[i + 1][0]
        if merged and merged[-1][0] == v:
            merged[-1][1] += n
        else:
            merged.append([v, n])
    return [v for v, n in merged for _ in range(n)]


def assemble(lines: list[dict], wavs: dict[str, Path], out_wav: Path) -> list[dict]:
    """The narration track: lines joined with their pauses, each dialogue line with its mouth shapes."""
    def mouth(ln: dict, data: bytes) -> dict:
        return {"mouth": "".join(map(str, mouth_levels(data)))} if "who" in ln else {}
    return audio.concat(lines, wavs, out_wav, extra=mouth)


# ---------- captions ----------

def caption_chunks(text: str) -> list[str]:
    """The text cut at BudouX phrase boundaries into cues of at most CAPTION_MAX chars."""
    chunks, cur = [], []
    for p in parser_ja.parse(text):
        if cur and len("".join(cur + [p])) > CAPTION_MAX:
            chunks.append("".join(cur))
            cur = []
        cur.append(p)
    chunks.append("".join(cur))
    return chunks


def cues_for(line: dict) -> list[dict]:
    chunks = caption_chunks(line["text"])
    total = sum(len(c) for c in chunks)
    t, span = line["start"], line["end"] - line["start"]
    out = []
    for c in chunks:
        d = span * len(c) / total
        out.append({"start": round(t, 3), "end": round(t + d, 3), "text": c, "html": wbr(c)})
        t += d
    return out


def vtt_time(s: float) -> str:
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{sec:06.3f}"


def write_vtt(timed: list[dict], path: Path) -> None:
    out = ["WEBVTT", ""]
    for ln in timed:
        for i, c in enumerate(ln["cues"]):
            out += [f"{ln['id']}-{i}", f"{vtt_time(c['start'])} --> {vtt_time(c['end'])}", c["text"], ""]
    path.write_text("\n".join(out))


# ---------- page ----------

def timeline(script: dict, timed: list[dict], duration: float) -> dict:
    chapters, scenes = [], []
    for ln in timed:
        if not chapters or chapters[-1]["id"] != ln["chapter"]:
            ch = next(c for c in script["chapters"] if c["id"] == ln["chapter"])
            chapters.append({"id": ch["id"], "title": ch["title"], "start": ln["start"]})
        if not scenes or scenes[-1]["id"] != ln["scene"]:
            scenes.append({"id": ln["scene"], "chapter": ln["chapter"], "kind": ln["kind"], "start": ln["start"]})
    for seq in (chapters, scenes):
        for a, b in zip(seq, seq[1:] + [None]):
            a["end"] = b["start"] if b else duration
    keys = ("id", "scene", "chapter", "idx", "text", "start", "end", "cues", "who", "face", "style_id", "mouth")
    lines = [{k: ln[k] for k in keys if k in ln} for ln in timed]
    return {"duration": duration, "chapters": chapters, "scenes": scenes, "lines": lines}


# Words a caption never breaks inside: BudouX splits some names (ずんだも|ん). Extended per project
# with the cast's names and the readings' surfaces.
KEEP_WHOLE = {"ずんだもん", "四国めたん", "めたん"}


def wbr(text: str) -> str:
    """Escape and allow line breaks only between BudouX phrases, never inside a KEEP_WHOLE word."""
    cuts, pos = [], 0
    for phrase in parser_ja.parse(text)[:-1]:
        pos += len(phrase)
        cuts.append(pos)
    inside = set()
    for word in KEEP_WHOLE:
        i = text.find(word)
        while i >= 0:
            inside.update(range(i + 1, i + len(word)))
            i = text.find(word, i + 1)
    out, last = [], 0
    for cut in cuts:
        if cut not in inside:
            out.append(text[last:cut])
            last = cut
    out.append(text[last:])
    return "<wbr>".join(html.escape(p) for p in out)


def quiz_section(scene_id: str, timed: list[dict]) -> str:
    q, a = [ln for ln in timed if ln["scene"] == scene_id]
    return (
        f'<section class="scene ev-quiz" data-scene="{scene_id}">'
        '<div class="ev-quiz-kicker">止めて考える</div>'
        f'<div class="ev-quiz-q">{wbr(q["text"])}</div>'
        '<div class="ev-quiz-bar"><i></i></div>'
        f'<div class="ev-quiz-a" data-at="1">{wbr(a["text"])}</div>'
        "</section>"
    )


def resolve_voices(cast: list[dict], lines: list[dict]) -> list[dict]:
    """Give each line its style id and return the engine's speakers (none for the bundled single narrator)."""
    return voices.resolve(cast, lines, cast_errors)


def make_unit(root: Path, uid: str, out: Path, bitrate: str) -> dict:
    """Synthesize, time and caption the video; write the unit bundle to `out` and return unit.json."""
    script, readings, cast, lines = load_project(root)
    if errs := source_errors(script.get("sources", [])) + claim_errors(script, lines) + assumes_errors(script):
        die("\n".join(errs))
    credit = narration_credit(script) if not cast else None
    speakers = resolve_voices(cast, lines)
    terms = terms_for(script, cast, lines, speakers)
    out.mkdir(parents=True, exist_ok=True)
    wavs = synth(lines, readings, voices.TTS_CACHE, float(script.get("speed", 1.0)))
    timed = assemble(lines, wavs, out / "narration.raw.wav")
    duration = round(timed[-1]["end"] + timed[-1]["pause"], 3)
    for ln in timed:
        ln["cues"] = cues_for(ln)
    encode(out / "narration.raw.wav", out / "narration.m4a", bitrate)
    write_vtt(timed, out / "captions.vtt")
    tl = timeline(script, timed, duration)
    names = {m["id"]: m["name"] for m in cast}

    def said(ln: dict) -> str:
        return f"{names[ln['who']]}: {ln['text']}" if cast else ln["text"]

    (out / "transcript.md").write_text("\n\n".join(
        f"## {c['title']}\n\n" + "\n".join(said(ln) for ln in timed if ln["chapter"] == c["id"]) for c in tl["chapters"]))

    scenes_html = out_implies_at((root / "scenes.html").read_text())
    declared = set(attr_values(scenes_html, "data-scene")["data-scene"])
    wanted = {s["id"] for s in tl["scenes"] if s["kind"] == "scene"}
    if wanted - declared:
        die(f"{root}/scenes.html is missing sections for: {', '.join(sorted(wanted - declared))}")
    if declared - wanted:
        print(f"warn: scenes.html has unused sections: {', '.join(sorted(declared - wanted))}")
    quizzes = "".join(quiz_section(s["id"], timed) for s in tl["scenes"] if s["kind"] == "quiz")
    font_css = ""
    if cast:
        # one family per unit: a course page holds several videos, each with its own subset
        tag = hashlib.sha1(uid.encode()).hexdigest()[:10]
        face = caption_font_css([ln["text"] for ln in timed], f"yes-cap-{tag}")
        if face:
            font_css = f'<style>{face}[data-cap="{tag}"]{{--ev-cap-font:"yes-cap-{tag}"}}</style>\n'
    cap_attr = f' data-cap="{tag}"' if font_css else ""
    (out / "unit.html").write_text(
        f'<div class="su-unit" data-unit="{html.escape(uid)}" data-kind="video"{cap_attr} hidden>\n{font_css}{scenes_html}\n{quizzes}\n</div>\n')
    for f in ("runtime.js", "runtime.css"):
        shutil.copy(SKILL_DIR / f, out / f)
    data = {"title": script.get("title", ""), "kicker": script.get("subtitle", ""), "goals": script.get("goals", []),
            "assumes": script.get("assumes", [])}
    if cast:
        data.update(cast=cast_data(cast, timed), credits=credits_for(timed, cast, speakers),
                    description=script.get("description", ""))
    else:
        data["credit"] = credit
    if script.get("sources"):
        data["sources"] = [{k: s[k] for k in ("title", "url", "note") if s.get(k)} for s in script["sources"]]
    if not cast and licensed():
        # A custom attribution must not replace the bundled narrator's required credit.
        data["credits"] = list(dict.fromkeys([voice_policy("ずんだもん")["credit"], credit]))
    data["usageTerms"] = terms
    data.update(timeline=tl, audio="data:audio/mp4;base64," + base64.b64encode((out / "narration.m4a").read_bytes()).decode())
    unit = {
        "id": uid, "kind": "video", "title": script.get("title", uid), "duration": duration,
        "outline": [{"rest": c["id"], "title": c["title"]} for c in tl["chapters"]],
        "data": data,
    }
    (out / "unit.json").write_text(json.dumps(unit, ensure_ascii=False))
    # what every line said, for reading them all through (narration skill's narration.json)
    manifest.write(out / "narration.json", manifest.build(
        lines, readings, wavs, speed=float(script.get("speed", 1.0)), cast=cast, speakers=speakers,
        credits=data.get("credits") or [credit], terms=terms, title=script.get("title", "")))
    for w in lint(lines, readings, {ln["id"]: ln["end"] - ln["start"] for ln in timed}) + claim_warnings(script, lines):
        print(f"warn: {w}")
    print(f"{uid}: {duration / 60:.1f} min, {len(timed)} lines")
    return unit


def cast_data(cast: list[dict], timed: list[dict]) -> list[dict]:
    """unit.json cast: art (only the faces the lines use, plus normal) or just name and color."""
    used: dict[str, set[str]] = {}
    for ln in timed:
        used.setdefault(ln["who"], {DEFAULT_FACE}).add(ln["face"])
    if any("char" in m for m in cast):
        sys.path.insert(0, str(SKILL_DIR))
        from characters import cast_entry
    return [cast_entry(m["id"], used.get(m["id"], {DEFAULT_FACE})) if "char" in m
            else {k: m[k] for k in ("id", "name", "color") if m.get(k)} for m in cast]


def standalone_page(unit_dir: Path) -> str:
    """One unit on its own page: the skill's page.html host plus the bundle."""
    unit = json.loads((unit_dir / "unit.json").read_text())
    data = json.dumps({"kind": unit["kind"], "data": unit["data"]}, ensure_ascii=False).replace("</", "<\\/")
    page = (SKILL_DIR / "page.html").read_text()
    for key, val in {
        "__TITLE__": html.escape(unit["title"]),
        "/*__CSS__*/": (unit_dir / "runtime.css").read_text(),
        "/*__JS__*/": (unit_dir / "runtime.js").read_text(),
        "<!--__UNIT__-->": (unit_dir / "unit.html").read_text().replace(" hidden>", ">", 1),
        "/*__DATA__*/null": data,
    }.items():
        if key not in page:
            die(f"page.html lost placeholder {key}")
        page = page.replace(key, val)
    return page


# ---------- commands ----------

def cmd_lint(root: Path) -> None:
    script, readings, cast, lines = load_project(root)
    if errs := source_errors(script.get("sources", [])) + claim_errors(script, lines) + assumes_errors(script):
        die("\n".join(errs))
    if not cast:
        narration_credit(script)
    chars = sum(len(ln["text"]) for ln in lines)
    print(f"{len(lines)} lines, {chars} chars ≈ {chars / 300:.1f} min at 300 chars/min")
    own = json.loads((root / "readings.json").read_text()) if (root / "readings.json").exists() else {}
    for w in (lint(lines, readings) + rd.space_warnings(lines, own) + claim_warnings(script, lines)
              + assumes_warnings(script)):
        print(f"warn: {w}")
    for ln in lines:
        for hint in rd.number_hints(rd.spoken(ln, readings)):
            print(f"listen: {ln['id']}: {hint}")
    if not cast:
        return
    styles = None
    try:
        styles = style_ids(list_speakers())
    except (OSError, RuntimeError, ValueError) as e:
        print(f"warn: speaker list failed ({e}); style names not checked")
    errs = cast_errors(lines, cast, styles)
    for e in errs:
        print(f"error: {e}")
    if errs:
        sys.exit(1)


def cmd_tts_plan(root: Path) -> None:
    """List every sentence that has no audio yet, with the file the build will read it from."""
    script, readings, cast, lines = load_project(root)
    resolve_voices(cast, lines)
    plan = voices.tts_plan(lines, readings, voices.TTS_CACHE, float(script.get("speed", 1.0)),
                           {m["id"]: m["speaker"] for m in cast})
    out = root / "out" / "tts-plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    print(f"{len(plan['items'])} sentences to synthesize -> {out}")


def cmd_build(root: Path) -> None:
    script = json.loads((root / "script.json").read_text())
    unit_dir = root / "out" / "unit"
    make_unit(root, script.get("id", "main"), unit_dir, script.get("bitrate", "48k"))
    for f in ("captions.vtt", "transcript.md", "narration.json"):
        shutil.copy(unit_dir / f, root / "out" / f)
    (root / "out" / "spoken.md").write_text(manifest.spoken_report(json.loads((unit_dir / "narration.json").read_text())))
    shutil.copy(unit_dir / "unit.json", root / "out" / "unit.json")
    page = root / "out" / "video.html"
    page.write_text(standalone_page(unit_dir))
    size = page.stat().st_size
    print(f"page {size / 1e6:.1f} MB -> {page}")


def cmd_shoot(root: Path, at: str, only: set[str] | None) -> None:
    tl = json.loads((root / "out" / "unit.json").read_text())["data"]["timeline"]
    frames = root / "out" / "frames"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir()
    url = (root / "out" / "video.html").resolve().as_uri()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        # the installed Chrome: no browser download needed
        browser = pw.chromium.launch(channel=os.environ.get("YES_BROWSER_CHANNEL", "chrome") or None)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(url)
        page.evaluate("document.fonts.ready")
        for s in tl["scenes"]:
            if only and s["id"] not in only:
                continue
            lines = [ln for ln in tl["lines"] if ln["scene"] == s["id"]]
            t = {"start": lines[0]["start"] + 0.3,
                 "mid": lines[len(lines) // 2]["start"] + 0.3,
                 "end": lines[-1]["start"] + 0.3}[at]
            page.evaluate(f"location.hash = 't={t:.2f}&shot'")
            page.wait_for_timeout(900)  # let build transitions finish
            png = frames / f"{s['id']}.png"
            page.screenshot(path=str(png))
            print(png)
        browser.close()


def cmd_check(root: Path) -> None:
    """Drive the built page: maximize and restore, with and without the Fullscreen API; frames in out/frames/_full-*.png."""
    from playwright.sync_api import sync_playwright
    from maximize_check import check_maximize

    tl = json.loads((root / "out" / "unit.json").read_text())["data"]["timeline"]
    url = (root / "out" / "video.html").resolve().as_uri() + f"#t={tl['duration'] / 2:.1f}"
    fails: list[str] = []

    def expect(ok: bool, what: str) -> None:
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=os.environ.get("YES_BROWSER_CHANNEL", "chrome") or None, args=["--autoplay-policy=no-user-gesture-required"])
        check_maximize(browser, url, ".su-unit.ev-video", expect, root / "out" / "frames")
        browser.close()
    if fails:
        die(f"{len(fails)} check(s) failed")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["lint", "build", "shoot", "unit", "check", "tts-plan"])
    ap.add_argument("project", type=Path)
    ap.add_argument("--at", default="end", choices=["start", "mid", "end"])
    ap.add_argument("--only")
    ap.add_argument("--id")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--bitrate", default="48k")
    ap.add_argument("--format", choices=["single", "bundle"], default="single")
    ap.add_argument("--max-bytes", type=int, help="Optional publishing-host HTML size limit")
    a = ap.parse_args()
    root = a.project.resolve()
    if a.cmd == "lint":
        cmd_lint(root)
    elif a.cmd == "build":
        cmd_build(root)
        export(root / "out" / "video.html", a.format, a.max_bytes)
    elif a.cmd == "check":
        cmd_check(root)
    elif a.cmd == "tts-plan":
        cmd_tts_plan(root)
    elif a.cmd == "unit":
        if not (a.id and a.out):
            die("unit needs --id and --out")
        make_unit(root, a.id, a.out.resolve(), a.bitrate)
    else:
        cmd_shoot(root, a.at, set(a.only.split(",")) if a.only else None)


if __name__ == "__main__":
    main()
