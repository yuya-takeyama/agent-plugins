# /// script
# requires-python = ">=3.11"
# dependencies = ["budoux>=0.6", "imageio-ffmpeg>=0.5", "playwright>=1.50"]
# ///
"""Build a narrated explainer video: a standalone HTML page, or a YESUnits unit for a course.

    uv run build.py lint  <project>   # script checks only, no synthesis
    uv run build.py build <project>   # synth (cached) -> timeline -> captions -> out/video.html
    uv run build.py shoot <project> [--at end|start|mid] [--only s3,s4]
    uv run build.py unit  <project> --id ID --out DIR [--bitrate 32k]   # unit bundle for course

<project>/script.json   narration, chapters, scenes, quizzes (see SKILL.md)
<project>/scenes.html   one <section class="scene" data-scene="ID"> per non-quiz scene
<project>/readings.json optional {"surface": "reading"} merged over the skill's readings.json

EV_TTS_CMD overrides the synthesis command (default bundled `yes-speak`).
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import math
import os
import hashlib
import html
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from array import array
from pathlib import Path

import budoux
import imageio_ffmpeg

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR.parents[1] / "scripts"))
from output import export
# shared across projects: a course rebuild reuses every sentence its lessons already synthesized
TTS_CACHE = Path(os.environ.get("EV_TTS_CACHE", Path.home() / ".cache" / "yes" / "tts"))
TTS_WORKERS = int(os.environ.get("EV_TTS_WORKERS", "4"))
RATE = 24000  # VOICEVOX output
LEAD_IN = 0.4
PAUSE_LINE = 0.35
PAUSE_SCENE = 0.9
PAUSE_CHAPTER = 1.4
QUIZ_THINK = 4.0
CAPTION_MAX = 40  # chars per cue (two lines of ~20)
LINE_WARN = 60
CPS_WARN = 7.5
DEICTIC = re.compile(r"この図|この部分|ここを|ここで見|こちら|この赤|この青|これを見")
ASCII_WORD = re.compile(r"[A-Za-z][A-Za-z0-9.+#'-]*")
CHARACTERS = SKILL_DIR / "characters"
DEFAULT_STYLE = "ノーマル"
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
    readings = json.loads((SKILL_DIR / "readings.json").read_text())
    if (root / "readings.json").exists():
        readings.update(json.loads((root / "readings.json").read_text()))
    cast = load_cast(script)
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
    return cast


def norm_line(raw) -> dict:
    line = {"text": raw} if isinstance(raw, str) else dict(raw)
    if not line.get("text"):
        die(f"line without text: {raw!r}")
    return line


def flatten(script: dict, cast: list[str] | None = None) -> list[dict]:
    """Every narrated line in order, with its scene/chapter and the pause after it.

    With a cast (ids), each line also gets `who` (default: the previous line's speaker),
    `style` (default ノーマル) and `face` (sticky per character)."""
    out: list[dict] = []
    explainer = cast[0] if cast else None
    who, faces = explainer, {}
    chapters = script["chapters"]
    for ci, ch in enumerate(chapters):
        scenes = list(ch["scenes"])
        if ch.get("quiz"):
            q = ch["quiz"]
            scenes.append({
                "id": f"{ch['id']}-quiz", "kind": "quiz",
                "lines": [
                    {"text": q["q"], "reading": q.get("q_reading"), "pause": q.get("think", QUIZ_THINK),
                     "who": q.get("q_who") or explainer},
                    {"text": q["a"], "reading": q.get("a_reading"), "who": q.get("a_who") or explainer},
                ],
            })
        for si, sc in enumerate(scenes):
            lines = [norm_line(ln) for ln in sc["lines"]]
            for li, line in enumerate(lines):
                last_in_scene = li == len(lines) - 1
                last_in_ch = last_in_scene and si == len(scenes) - 1
                default = PAUSE_CHAPTER if last_in_ch else PAUSE_SCENE if last_in_scene else PAUSE_LINE
                if ci == len(chapters) - 1 and last_in_ch:
                    default = 1.0
                entry = {
                    "id": f"{sc['id']}.{li}", "chapter": ch["id"], "scene": sc["id"],
                    "kind": sc.get("kind", "scene"), "idx": li,
                    "text": line["text"], "reading": line.get("reading"),
                    "pause": float(line.get("pause") if line.get("pause") is not None else default),
                }
                if cast:
                    who = line.get("who") or who
                    faces[who] = line.get("face") or faces.get(who, DEFAULT_FACE)
                    entry.update(who=who, style=line.get("style") or DEFAULT_STYLE, face=faces[who])
                out.append(entry)
    return out


def reading_of(line: dict, readings: dict) -> str:
    if line.get("reading"):
        return line["reading"]
    text = line["text"]
    for surface in sorted(readings, key=len, reverse=True):
        # ASCII surfaces match whole words only, so "AI" never fires inside "MAIN"
        pat = re.escape(surface)
        if surface.isascii():
            pat = rf"(?<![A-Za-z0-9]){pat}(?![A-Za-z0-9])"
        text = re.sub(pat, lambda _, r=readings[surface]: r, text)
    return text


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


def lint(lines: list[dict], readings: dict, durations: dict | None = None) -> list[str]:
    warns = []
    for ln in lines:
        t = ln["text"]
        if len(t) > LINE_WARN:
            warns.append(f"{ln['id']}: {len(t)} chars (> {LINE_WARN}); split the sentence")
        if DEICTIC.search(t):
            warns.append(f"{ln['id']}: deictic phrase '{DEICTIC.search(t).group()}' — name the thing so audio-only works")
        if not ln.get("reading"):
            spoken = reading_of(ln, readings)
            left = [w for w in ASCII_WORD.findall(spoken) if len(w) > 1]
            if left:
                warns.append(f"{ln['id']}: no reading for {', '.join(sorted(set(left)))} — add to readings.json or give the line a reading")
        if durations and ln["id"] in durations:
            cps = len(t) / max(durations[ln["id"]], 0.1)
            if cps > CPS_WARN:
                warns.append(f"{ln['id']}: {cps:.1f} chars/s on screen (> {CPS_WARN})")
        # the dialogue layout has room for two caption lines between the characters
        if "who" in ln and len(caption_chunks(t)) > 2:
            warns.append(f"{ln['id']}: caption runs over 2 lines; split the sentence")
    return warns


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

def tts_cmd() -> list[str]:
    return shlex.split(os.environ["EV_TTS_CMD"]) if os.environ.get("EV_TTS_CMD") else [sys.executable, str(SKILL_DIR.parents[1] / "scripts" / "yes_speak.py")]


def list_speakers() -> list[dict]:
    """`<tts> --list-speakers --json`: [{name, styles: [{name, id, type}], credit}]."""
    r = subprocess.run([*tts_cmd(), "--list-speakers", "--json"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"exit {r.returncode}")
    return json.loads(r.stdout)


def style_ids(speakers: list[dict]) -> dict[tuple[str, str], int]:
    return {(sp["name"], st["name"]): st["id"]
            for sp in speakers for st in sp["styles"] if st.get("type", "talk") == "talk"}


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
    if os.environ.get("EV_TTS_CMD"):
        die('A single-narrator script using EV_TTS_CMD needs a nonempty "credit".')
    return "VOICEVOX:ずんだもん"


# ---------- synthesis ----------

def cache_key(spoken: str, speed: float, style_id: int | None) -> str:
    # Include backend identity so a provider change never reuses incompatible audio.
    src = f"{speed}|{spoken}" if style_id is None else f"{style_id}|{speed}|{spoken}"
    src = "yes-voicevox-0.25.2|" + os.environ.get("EV_TTS_CMD", "bundled") + "|" + src
    return hashlib.sha1(src.encode()).hexdigest()[:16]


def synth(lines: list[dict], readings: dict, cache: Path, speed: float) -> dict[str, Path]:
    cache.mkdir(parents=True, exist_ok=True)
    tts = tts_cmd()
    jobs = {}
    for ln in lines:
        spoken = reading_of(ln, readings)
        style_id = ln.get("style_id")
        jobs[ln["id"]] = (spoken, style_id, cache / f"{cache_key(spoken, speed, style_id)}.wav")

    todo = {p: (s, sid) for s, sid, p in jobs.values() if not p.exists()}
    print(f"synth: {len(jobs)} lines, {len(todo)} new")

    def run(item):
        path, (spoken, style_id) = item
        with tempfile.NamedTemporaryFile(dir=cache, prefix=path.stem + ".", suffix=".wav", delete=False) as file:
            tmp = Path(file.name)
        try:
            cmd = [*tts, "--text", spoken, "-o", str(tmp), "--force", "--speed", str(speed)]
            if style_id is not None:
                cmd += ["--speaker", str(style_id)]
            for attempt in range(6):
                r = subprocess.run(cmd, capture_output=True, text=True)
                # the shared VOICEVOX endpoint answers 429 when several builds run at once
                if r.returncode == 0 or "429" not in r.stderr:
                    break
                time.sleep(2 ** attempt)
            if r.returncode != 0:
                return f"{spoken[:30]}…: {r.stderr.strip()}"
            os.replace(tmp, path)
            return None
        finally:
            tmp.unlink(missing_ok=True)

    with cf.ThreadPoolExecutor(max_workers=TTS_WORKERS) as pool:
        for i, err in enumerate(pool.map(run, todo.items()), 1):
            if err:
                die(f"{tts[0]} failed: {err}")
            if i % 10 == 0:
                print(f"  {i}/{len(todo)}")
    return {lid: p for lid, (_, _, p) in jobs.items()}


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path)) as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (RATE, 1, 2):
            die(f"{path}: expected {RATE}Hz mono 16-bit")
        return w.readframes(w.getnframes())


def mouth_levels(pcm: bytes) -> list[int]:
    """Per 1/MOUTH_FPS s frame: 0 closed, 1 half, 2 open, from RMS normalized to the line."""
    samples = array("h", pcm)
    if sys.byteorder == "big":
        samples.byteswap()
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
    pcm = bytearray(b"\0\0" * int(LEAD_IN * RATE))
    timed = []
    for ln in lines:
        data = read_pcm(wavs[ln["id"]])
        start = len(pcm) / 2 / RATE
        pcm += data
        end = len(pcm) / 2 / RATE
        pcm += b"\0\0" * int(ln["pause"] * RATE)
        item = {**ln, "start": round(start, 3), "end": round(end, 3)}
        if "who" in ln:
            item["mouth"] = "".join(map(str, mouth_levels(data)))
        timed.append(item)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(pcm))
    return timed


def encode(raw_wav: Path, out_m4a: Path, bitrate: str) -> None:
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    probe = subprocess.run(
        [ff, "-hide_banner", "-i", str(raw_wav), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    m = json.loads(probe[probe.rindex("{"):probe.rindex("}") + 1])
    af = (
        "loudnorm=I=-16:TP=-1.5:LRA=11:linear=true"
        f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
        f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}"
    )
    subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_wav), "-af", af,
         "-ar", str(RATE), "-ac", "1", "-c:a", "aac", "-b:a", bitrate, str(out_m4a)],
        check=True,
    )


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


def wbr(text: str) -> str:
    """Escape and allow line breaks only between BudouX phrases."""
    return "<wbr>".join(html.escape(p) for p in parser_ja.parse(text))


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


def make_unit(root: Path, uid: str, out: Path, bitrate: str) -> dict:
    """Synthesize, time and caption the video; write the unit bundle to `out` and return unit.json."""
    script, readings, cast, lines = load_project(root)
    credit = narration_credit(script) if not cast else None
    speakers: list[dict] = []
    if cast:
        try:
            speakers = list_speakers()
        except (OSError, RuntimeError, ValueError) as e:
            die(f"{shlex.join(tts_cmd())} --list-speakers --json failed: {e}")
        styles = style_ids(speakers)
        errs = cast_errors(lines, cast, styles)
        if errs:
            die("\n".join(errs))
        speaker_of = {m["id"]: m["speaker"] for m in cast}
        for ln in lines:
            ln["style_id"] = styles[(speaker_of[ln["who"]], ln["style"])]
    out.mkdir(parents=True, exist_ok=True)
    wavs = synth(lines, readings, TTS_CACHE, float(script.get("speed", 1.0)))
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
    declared = set(re.findall(r'data-scene="([^"]+)"', scenes_html))
    wanted = {s["id"] for s in tl["scenes"] if s["kind"] == "scene"}
    if wanted - declared:
        die(f"{root}/scenes.html is missing sections for: {', '.join(sorted(wanted - declared))}")
    if declared - wanted:
        print(f"warn: scenes.html has unused sections: {', '.join(sorted(declared - wanted))}")
    quizzes = "".join(quiz_section(s["id"], timed) for s in tl["scenes"] if s["kind"] == "quiz")
    (out / "unit.html").write_text(
        f'<div class="su-unit" data-unit="{html.escape(uid)}" data-kind="video" hidden>\n{scenes_html}\n{quizzes}\n</div>\n')
    for f in ("runtime.js", "runtime.css"):
        shutil.copy(SKILL_DIR / f, out / f)
    data = {"title": script.get("title", ""), "kicker": script.get("subtitle", ""), "goals": script.get("goals", [])}
    if cast:
        data.update(cast=cast_data(cast, timed), credits=credits_for(timed, cast, speakers),
                    description=script.get("description", ""))
    else:
        data["credit"] = credit
    data.update(timeline=tl, audio="data:audio/mp4;base64," + base64.b64encode((out / "narration.m4a").read_bytes()).decode())
    unit = {
        "id": uid, "kind": "video", "title": script.get("title", uid), "duration": duration,
        "outline": [{"rest": c["id"], "title": c["title"]} for c in tl["chapters"]],
        "data": data,
    }
    (out / "unit.json").write_text(json.dumps(unit, ensure_ascii=False))
    for w in lint(lines, readings, {ln["id"]: ln["end"] - ln["start"] for ln in timed}):
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
    if not cast:
        narration_credit(script)
    chars = sum(len(ln["text"]) for ln in lines)
    print(f"{len(lines)} lines, {chars} chars ≈ {chars / 300:.1f} min at 300 chars/min")
    for w in lint(lines, readings):
        print(f"warn: {w}")
    if not cast:
        return
    styles = None
    try:
        styles = style_ids(list_speakers())
    except (OSError, RuntimeError, ValueError) as e:
        print(f"warn: {shlex.join(tts_cmd())} --list-speakers --json failed ({e}); style names not checked")
    errs = cast_errors(lines, cast, styles)
    for e in errs:
        print(f"error: {e}")
    if errs:
        sys.exit(1)


def cmd_build(root: Path) -> None:
    script = json.loads((root / "script.json").read_text())
    unit_dir = root / "out" / "unit"
    make_unit(root, script.get("id", "main"), unit_dir, script.get("bitrate", "48k"))
    for f in ("captions.vtt", "transcript.md"):
        shutil.copy(unit_dir / f, root / "out" / f)
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["lint", "build", "shoot", "unit"])
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
    elif a.cmd == "unit":
        if not (a.id and a.out):
            die("unit needs --id and --out")
        make_unit(root, a.id, a.out.resolve(), a.bitrate)
    else:
        cmd_shoot(root, a.at, set(a.only.split(",")) if a.only else None)


if __name__ == "__main__":
    main()
