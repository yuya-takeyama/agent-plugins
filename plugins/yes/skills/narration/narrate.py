# /// script
# requires-python = ">=3.11"
# dependencies = ["imageio-ffmpeg>=0.5"]
# ///
"""Narration from a script: readings, lint, cached VOICEVOX synthesis, checks, and a mixed m4a/mp3.

    uv run narrate.py lint    <project>   # script and readings checks, no audio
    uv run narrate.py spoken  <project>   # every line's caption and spoken text -> out/spoken.md
    uv run narrate.py synth   <project>   # synthesize changed lines -> out/narration.json, out/narration/*.wav
    uv run narrate.py check   <project>   # loudness, silence and caption speed of the synthesized lines
    uv run narrate.py credits <project>   # the credits and terms to show with the audio
    uv run narrate.py mix     <project> [--format m4a|mp3] [--bitrate 64k]   # join, BGM, loudness -> out/<id>.<fmt>
    uv run narrate.py build   <project>   # synth, check, mix
    uv run narrate.py tts-plan <project>  # YES_TTS_FILES: the sentences still to write as WAV files
    uv run narrate.py say 'TrueTime です' [--project DIR]   # one string through the readings

<project>/script.json    chapters -> (scenes ->) lines, optional cast, pauses, readings, bgm
<project>/readings.json  optional {"表記": "よみ"} merged over this skill's readings.json

A video project (yes:video, yes:zundamon-video) is a valid project too: lint and spoken work on
its script.json unchanged (synth, check and mix as well, into its out/ beside the video's files). Speech sources: see references/engines.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from narration import audio, die, manifest, voices  # noqa: E402
from narration import reading as rd  # noqa: E402
from narration import script as sc  # noqa: E402
from voice_licenses import SUPPORTED_VOICES, usage_notice, voice_policy  # noqa: E402  (path set by voices)


def load(root: Path) -> tuple[dict, dict, list[dict], list[dict], dict]:
    path = root / "script.json"
    if not path.exists():
        die(f"{path} not found")
    script = json.loads(path.read_text())
    readings = rd.load_readings(root / "readings.json", script.get("readings"))
    cast = sc.load_cast(script)
    if voices.licensed():
        for member in cast:
            if member["speaker"] not in SUPPORTED_VOICES:
                die("YES supports only ずんだもん and 四国めたん as VOICEVOX voices in the cast.")
    pauses = sc.pauses_for(script)
    return script, readings, cast, sc.flatten(script, [m["id"] for m in cast], pauses), pauses


def resolve(cast: list[dict], lines: list[dict]) -> list[dict]:
    return voices.resolve(cast, lines, sc.check_cast)


def credits(script: dict, cast: list[dict], lines: list[dict], speakers: list[dict]) -> list[str]:
    """Each voice's credit in order of first appearance; a non-VOICEVOX engine's from script.credit."""
    if not voices.licensed():
        credit = script.get("credit")
        if not (isinstance(credit, str) and credit.strip()):
            die('YES_TTS_ENGINE=other needs a nonempty "credit" in script.json.')
        return [credit.strip()]
    if not cast:
        return [voice_policy(voices.DEFAULT_NARRATOR[0])["credit"]]
    speaker_of = {m["id"]: m["speaker"] for m in cast}
    credit_of = voices.credit_of(speakers)
    out: list[str] = []
    for ln in lines:
        c = credit_of.get(speaker_of[ln["who"]]) or voice_policy(speaker_of[ln["who"]])["credit"]
        if c not in out:
            out.append(c)
    return out


def terms(script: dict, cast: list[dict], lines: list[dict], speakers: list[dict]) -> dict:
    if not voices.licensed():
        return script.get("usageTerms", {})
    used = {m["speaker"] for m in cast if any(ln["who"] == m["id"] for ln in lines)} if cast else {voices.DEFAULT_NARRATOR[0]}
    by_name = {sp["name"]: sp for sp in speakers}
    voiced = [by_name.get(name) or {"name": name, **voice_policy(name)} for name in sorted(used)]
    return usage_notice(voiced, [], pinned=voices.pinned())


# ---------- commands ----------

def cmd_lint(root: Path) -> int:
    script, readings, cast, lines, _ = load(root)
    chars = sum(len(ln["text"]) for ln in lines)
    print(f"{len(lines)} lines, {chars} chars ≈ {chars / 300:.1f} min at 300 chars/min")
    project_readings = rd.load_readings(root / "readings.json", script.get("readings"))
    seed = json.loads(rd.SEED.read_text())
    own = {k: v for k, v in project_readings.items() if seed.get(k) != v}
    for w in [*(w for ln in lines for w in rd.line_warnings(ln, readings)), *rd.space_warnings(lines, own)]:
        print(f"warn: {w}")
    for ln in lines:
        for hint in rd.number_hints(rd.spoken(ln, readings)):
            print(f"listen: {ln['id']}: {hint}")
    if not cast:
        return 0
    try:
        styles = voices.style_ids(voices.list_speakers())
    except (OSError, RuntimeError, ValueError) as e:
        print(f"warn: speaker list failed ({e}); style names not checked")
        styles = None
    errs = sc.check_cast(lines, cast, styles)
    for e in errs:
        print(f"error: {e}")
    return 1 if errs else 0


def cmd_spoken(root: Path) -> None:
    script, readings, _, lines, _ = load(root)
    items = []
    for ln in lines:
        said = rd.spoken(ln, readings)
        item = {"id": ln["id"], "who": ln.get("who"), "text": ln["text"], "spoken": said}
        if hints := rd.number_hints(said):
            item["listen"] = hints
        items.append(item)
    report = manifest.spoken_report({"title": script.get("title", ""), "lines": items})
    out = root / "out" / "spoken.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print(report, end="")
    print(f"-> {out}")


def cmd_synth(root: Path) -> dict:
    script, readings, cast, lines, _ = load(root)
    speakers = resolve(cast, lines)
    speed = float(script.get("speed", 1.0))
    wavs = voices.synth(lines, readings, voices.TTS_CACHE, speed)
    m = manifest.build(lines, readings, wavs, speed=speed, cast=cast, speakers=speakers,
                       credits=credits(script, cast, lines, speakers), terms=terms(script, cast, lines, speakers),
                       title=script.get("title", ""), copy_to=root / "out" / "narration", base=root / "out")
    previous = root / "out" / "narration.json"
    if m["engine"]["version"] is None and previous.exists():
        # every line came from the cache: the version recorded when they were synthesized still holds
        old = json.loads(previous.read_text()).get("engine") or {}
        if old.get("source") == m["engine"]["source"]:
            m["engine"]["version"] = old.get("version")
    manifest.write(previous, m)
    (root / "out" / "spoken.md").write_text(manifest.spoken_report(m))
    total = sum(it["seconds"] + (it["pause"] or 0) for it in m["lines"])
    print(f"{len(m['lines'])} lines, {total / 60:.1f} min -> {root / 'out' / 'narration.json'}")
    return m


def read_manifest(root: Path) -> dict:
    path = root / "out" / "narration.json"
    if not path.exists():
        die(f"{path} not found; run synth first")
    m = json.loads(path.read_text())
    if not m.get("lines"):
        die(f"{path} has no lines")
    if any("file" not in it for it in m["lines"]):
        # a video build's narration.json records the lines but keeps the audio in the cache
        die(f"{path} has no audio files; run `narrate.py synth {root}` first")
    return m


def cmd_check(root: Path) -> int:
    m = read_manifest(root)
    stats, warns = {}, []
    for it in m["lines"]:
        wav = root / "out" / it["file"]
        if manifest.sha256(wav) != it["sha256"]:
            warns.append(f"{it['id']}: {it['file']} does not match narration.json; run synth again")
            continue
        stats[it["id"]] = audio.measure(audio.read_pcm(wav))
        if w := rd.cps_warning(it, it["seconds"]):
            warns.append(w)
    warns += audio.level_warnings(stats)
    for w in warns:
        print(f"warn: {w}")
    print(f"checked {len(stats)} lines: {len(warns)} to look at")
    return 0


def cmd_credits(root: Path) -> None:
    m = read_manifest(root)
    print("\n".join(m["credits"]))
    t = m.get("usageTerms") or {}
    if t.get("text"):
        print("\n" + t["text"])
    for link in t.get("links", []):
        print(f"- {link['title']}: {link['url']}")
    if m["engine"]["name"] == "VOICEVOX":
        print("\nAudio-only: say the credit in the audio or put it in the show notes / description next to the player.")


def cmd_mix(root: Path, fmt: str, bitrate: str) -> Path:
    script = json.loads((root / "script.json").read_text())
    pauses = sc.pauses_for(script)
    m = read_manifest(root)
    out = root / "out"
    wavs = {it["id"]: out / it["file"] for it in m["lines"]}
    lines = [{"id": it["id"], "chapter": it["chapter"], "pause": it["pause"], "who": it.get("who"),
              "text": it["text"]} for it in m["lines"]]
    voice = out / "narration.raw.wav"
    timed = audio.concat(lines, wavs, voice, lead_in=pauses["lead_in"])
    duration = round(timed[-1]["end"] + timed[-1]["pause"], 3)
    chapters = sc.chapter_spans(script, timed, duration)
    if chapters:
        chapters[0]["start"] = 0.0
    src = voice
    bgm = script.get("bgm")
    if bgm:
        if not isinstance(bgm, dict) or not isinstance(bgm.get("file"), str):
            die('bgm: {"file": "music.mp3", "gain": -24, "duck": true, "fade": 3}')
        music = (root / bgm["file"]).resolve()
        if not music.is_file():
            die(f"bgm file not found: {music}")
        src = out / "narration.mix.wav"
        audio.mix_bgm(voice, music, src, gain_db=float(bgm.get("gain", -24)), duck=bool(bgm.get("duck", True)),
                      fade=float(bgm.get("fade", 3)))
    name = script.get("id", "narration")
    target = out / f"{name}.{fmt}"
    meta = audio.chapters_metadata(script.get("title", name), chapters, duration, ", ".join(m["credits"]))
    audio.export(src, target, fmt, bitrate, meta)
    cast = {c["id"]: c["name"] for c in sc.load_cast(script)}
    (out / "timeline.json").write_text(json.dumps({
        "duration": duration, "chapters": chapters,
        "lines": [{k: ln[k] for k in ("id", "chapter", "who", "text", "start", "end") if ln.get(k) is not None}
                  for ln in timed]}, ensure_ascii=False, indent=1) + "\n")
    body = [f"# {script.get('title', name)}", ""]
    for ch in chapters:
        body += [f"## {ch['title']}", ""]
        body += [f"{cast[ln['who']]}: {ln['text']}" if ln.get("who") in cast else ln["text"]
                 for ln in timed if ln["chapter"] == ch["id"]]
        body.append("")
    body += ["---", "", *m["credits"]]
    (out / "transcript.md").write_text("\n".join(body) + "\n")
    print(f"{duration / 60:.1f} min, {audio.probe_loudness(target):.1f} LUFS -> {target}")
    return target


def cmd_tts_plan(root: Path) -> None:
    script, readings, cast, lines, _ = load(root)
    resolve(cast, lines)
    plan = voices.tts_plan(lines, readings, voices.TTS_CACHE, float(script.get("speed", 1.0)),
                           {m["id"]: m["speaker"] for m in cast})
    out = root / "out" / "tts-plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    print(f"{len(plan['items'])} sentences to synthesize -> {out}")


def cmd_say(text: str, project: Path | None) -> None:
    overlays = []
    if project:
        script = json.loads((project / "script.json").read_text()) if (project / "script.json").exists() else {}
        overlays = [project / "readings.json", script.get("readings")]
    readings = rd.load_readings(*overlays)
    said = rd.spoken({"id": "say", "text": text}, readings)
    print(said)
    for w in rd.unread_words(said):
        print(f"warn: no reading for {w}", file=sys.stderr)
    for hint in rd.number_hints(said):
        print(f"listen: {hint}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["lint", "spoken", "synth", "check", "credits", "mix", "build", "tts-plan", "say"])
    ap.add_argument("target", help="project directory (say: the text)")
    ap.add_argument("--format", choices=sorted(audio.FORMATS), default="m4a")
    ap.add_argument("--bitrate", default="64k")
    ap.add_argument("--project", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "say":
        cmd_say(a.target, a.project)
        return 0
    root = Path(a.target).resolve()
    if a.cmd == "lint":
        return cmd_lint(root)
    if a.cmd == "spoken":
        cmd_spoken(root)
    elif a.cmd == "synth":
        cmd_synth(root)
    elif a.cmd == "check":
        return cmd_check(root)
    elif a.cmd == "credits":
        cmd_credits(root)
    elif a.cmd == "mix":
        cmd_mix(root, a.format, a.bitrate)
    elif a.cmd == "build":
        cmd_synth(root)
        cmd_check(root)
        cmd_mix(root, a.format, a.bitrate)
        cmd_credits(root)
    else:
        cmd_tts_plan(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
