"""narration.json: for every line what is shown, what is said, by whom, how long, and the audio's hash.

It is the record a person reads to check every reading, and what a later rebuild compares against:
a line whose (voice, speed, spoken text) is unchanged keeps its audio.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from . import audio, voices
from .reading import number_hints, spoken

FORMAT = 1


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(lines: list[dict], readings: dict, wavs: dict[str, Path], *, speed: float, cast: list[dict],
          speakers: list[dict], credits: list[str], terms: dict, title: str = "",
          copy_to: Path | None = None, base: Path | None = None) -> dict:
    """The manifest. With `copy_to`, each WAV is also copied there (named by its cache key) and `file`
    is relative to `base`, so the project carries its own audio; stale copies are removed."""
    speaker_of = {m["id"]: m["speaker"] for m in cast}
    credit_of = voices.credit_of(speakers)
    b = voices.backend()
    narrator = voices.DEFAULT_NARRATOR[0] if voices.licensed() else None
    items, keep = [], set()
    for ln in lines:
        wav = wavs[ln["id"]]
        speaker = speaker_of.get(ln.get("who"), narrator)
        pcm = audio.read_pcm(wav)
        item = {
            "id": ln["id"], "chapter": ln.get("chapter"), "text": ln["text"], "spoken": spoken(ln, readings),
            "who": ln.get("who"), "speaker": speaker, "style": ln.get("style", voices.DEFAULT_NARRATOR[1]),
            "style_id": ln.get("style_id"), "speed": speed, "seconds": round(audio.seconds(pcm), 3),
            "pause": ln.get("pause"), "sha256": sha256(wav), "key": wav.stem,
            "credit": credit_of.get(speaker) or (f"VOICEVOX:{speaker}" if voices.licensed() and speaker else None),
        }
        if hints := number_hints(item["spoken"]):
            item["listen"] = hints
        if copy_to is not None:
            copy_to.mkdir(parents=True, exist_ok=True)
            dest = copy_to / wav.name
            if not dest.exists() or sha256(dest) != item["sha256"]:
                shutil.copyfile(wav, dest)
            keep.add(dest.name)
            item["file"] = str(dest.relative_to(base)) if base else str(dest)
        items.append(item)
    if copy_to is not None and copy_to.exists():
        for stale in copy_to.glob("*.wav"):
            if stale.name not in keep:
                stale.unlink()
    return {
        "format": FORMAT, "title": title,
        "engine": {"name": "VOICEVOX" if voices.licensed() else "other", "source": b["kind"],
                   "version": voices.engine_version()},
        "credits": credits, "usageTerms": terms, "lines": items,
    }


def write(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")


def spoken_report(manifest: dict) -> str:
    """Every line as a person checks it: caption, then what the engine was asked to say."""
    out = [f"# {manifest.get('title') or 'narration'} — spoken text", "",
           "Read every line: `text` is the caption, `say` is what VOICEVOX reads. "
           "Lines marked 👂 need listening.", ""]
    for it in manifest["lines"]:
        who = f" {it['who']}" if it.get("who") else ""
        length = f" ({it['seconds']} s)" if it.get("seconds") is not None else ""
        out.append(f"- `{it['id']}`{who}{length}")
        out.append(f"  - text: {it['text']}")
        if it["spoken"] != it["text"]:
            out.append(f"  - say:  {it['spoken']}")
        for hint in it.get("listen", []):
            out.append(f"  - 👂 {hint}")
    return "\n".join(out) + "\n"
