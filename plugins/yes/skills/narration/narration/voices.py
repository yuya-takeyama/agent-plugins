"""Where speech comes from, and synthesis with a per-sentence cache.

| source                         | set                                              |
|--------------------------------|--------------------------------------------------|
| bundled yes-speak, local Docker| nothing                                          |
| bundled yes-speak, other engine| YES_VOICEVOX_URL (a VOICEVOX engine's base URL)  |
| a jobs API (POST /jobs)        | YES_VOICEVOX_URL and YES_VOICEVOX_API=jobs       |
| a command                      | YES_TTS_CMD (alias EV_TTS_CMD), YES_TTS_ENGINE   |
| WAVs the agent writes          | YES_TTS_FILES=1, YES_TTS_ENGINE, YES_TTS_SPEAKERS|

VOICEVOX output keeps YES's voice restriction, credits and terms whichever way it arrives.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from . import die
from .reading import spoken

SKILL_DIR = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS = SKILL_DIR.parents[1] / "scripts"
sys.path.insert(0, str(PLUGIN_SCRIPTS))
from voice_licenses import SUPPORTED_VOICES, voice_policy  # noqa: E402

# shared across projects: a course rebuild reuses every sentence its lessons already synthesized
TTS_CACHE = Path(os.environ.get("EV_TTS_CACHE", Path.home() / ".cache" / "yes" / "tts"))
TTS_WORKERS = int(os.environ.get("EV_TTS_WORKERS", "4"))
PINNED_ENGINE = "0.25.2"  # the bundled yes-speak engine; scripts/yes_speak.py VERSION
DEFAULT_NARRATOR = ("ずんだもん", "ノーマル")
JOB_LIMIT = 500
JOBS_SEEN: dict[str, str] = {}  # engine version read from a jobs API's artifact keys this run


def engine_url() -> str:
    return os.environ.get("YES_VOICEVOX_URL", "").strip().rstrip("/")


def backend() -> dict:
    """Where speech comes from. `engine` voicevox puts the VOICEVOX voice restriction, credits and terms on it."""
    cmd = os.environ.get("YES_TTS_CMD") or os.environ.get("EV_TTS_CMD") or ""
    files = os.environ.get("YES_TTS_FILES", "") not in ("", "0")
    engine = os.environ.get("YES_TTS_ENGINE", "")
    url = engine_url()
    api = os.environ.get("YES_VOICEVOX_API", "") or "engine"
    if engine not in ("", "voicevox", "other"):
        die("YES_TTS_ENGINE must be voicevox or other.")
    if api not in ("engine", "jobs"):
        die("YES_VOICEVOX_API must be engine or jobs.")
    if cmd and files:
        die("Set YES_TTS_CMD or YES_TTS_FILES, not both.")
    if files and not engine:
        die("YES_TTS_FILES needs YES_TTS_ENGINE=voicevox or YES_TTS_ENGINE=other.")
    if cmd:
        # VOICEVOX unless declared otherwise: dropping its rules takes an explicit YES_TTS_ENGINE=other
        return {"kind": "cmd", "engine": engine or "voicevox", "cmd": shlex.split(cmd),
                "id": cmd + (f"|{url}" if url else "")}
    if files:
        return {"kind": "files", "engine": engine, "cmd": None, "id": "files:" + engine}
    if engine == "other":
        die("YES_TTS_ENGINE=other needs YES_TTS_CMD or YES_TTS_FILES; the bundled engine is VOICEVOX.")
    if api == "jobs":
        if not url:
            die("YES_VOICEVOX_API=jobs needs YES_VOICEVOX_URL, the API's base URL.")
        return {"kind": "jobs", "engine": "voicevox", "cmd": None, "id": "jobs:" + url, "url": url}
    # yes-speak reads YES_VOICEVOX_URL itself; another engine never shares the local engine's cache
    return {"kind": "bundled", "engine": "voicevox", "id": f"url:{url}" if url else "bundled", "url": url or None,
            "cmd": [sys.executable, str(PLUGIN_SCRIPTS / "yes_speak.py")]}


def licensed() -> bool:
    """True when the audio is VOICEVOX, whose voices and terms YES enforces whichever way it is produced."""
    return backend()["engine"] == "voicevox"


def pinned() -> bool:
    """Only the bundled local engine has a known version, so only it links version-pinned terms."""
    b = backend()
    return b["kind"] == "bundled" and not b["url"]


def names_narrator() -> bool:
    """A VOICEVOX narrator from anything but the local yes-speak is named by style id, never left to
    that engine's default voice."""
    b = backend()
    return licensed() and b["kind"] in ("cmd", "files", "jobs")


def tts_cmd() -> list[str]:
    cmd = backend()["cmd"]
    if not cmd:
        die("This speech source runs no command; see `tts-plan` (files) or YES_VOICEVOX_API (jobs).")
    return cmd


def run_tts(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a TTS command, waiting out a shared VOICEVOX endpoint when it is saturated:
    429 when several builds run at once, 503 when its speaker list is not ready yet."""
    for attempt in range(6):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 or not re.search(r"HTTP (429|503)\b", r.stderr):
            return r
        time.sleep(2 ** attempt)
    return r


# ---------- HTTP (jobs API) ----------

def http_json(url: str, data: dict | None = None, *, timeout: float = 60) -> tuple[int, dict]:
    """(status, JSON body). A network failure is status 0 with {"error": ...}, so callers retry or stop cleanly."""
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read() or b"{}")
        except ValueError:
            payload = {}
        return e.code, payload
    except (urllib.error.URLError, OSError, ValueError) as e:
        return 0, {"error": str(e)}


RETRY = (0, 429, 502, 503, 504)


def http_bytes(url: str, timeout: float = 120) -> bytes:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, OSError) as e:
            if attempt == 3:
                raise RuntimeError(f"download failed: {e}") from e
            time.sleep(2 ** attempt)
    raise AssertionError


def jobs_speakers(url: str) -> list[dict]:
    for attempt in range(6):
        status, body = http_json(url + "/speakers")
        if status == 200 and isinstance(body, list):
            return body
        if status not in RETRY:
            raise RuntimeError(f"GET /speakers: HTTP {status} {body}")
        time.sleep(2 ** attempt)
    raise RuntimeError(f"GET /speakers: HTTP {status}")


def validate_wav(data: bytes) -> None:
    with wave.open(io.BytesIO(data)) as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (24000, 1, 2) or not w.getnframes():
            raise RuntimeError("expected a nonempty 24000 Hz mono 16-bit WAV")


def jobs_synth(url: str, todo: dict[Path, tuple[str, int | None]], speed: float, *,
               poll: float = 2.0, deadline: float = 900, log=print) -> None:
    """Send every missing sentence as POST /jobs batches, wait for them, and write each WAV to its cache path.
    The same items give the same job, so a rerun after a failure retries only the failed sentences."""
    entries = list(todo.items())
    for i in range(0, len(entries), JOB_LIMIT):
        batch = entries[i:i + JOB_LIMIT]
        items = [{"text": s, "speaker": sid if sid is not None else 3, "speedScale": speed, "intonationScale": 1}
                 for _, (s, sid) in batch]
        for attempt in range(60):
            status, job = http_json(url + "/jobs", {"items": items})
            if status not in RETRY:
                break
            time.sleep(5)
        if status not in (200, 202) or "id" not in job:
            die(f"POST /jobs: HTTP {status} {job.get('error', '')}")
        log(f"  job {job['id'][:12]}: {len(batch)} sentences")
        stop = time.monotonic() + deadline
        while True:
            status, state = http_json(f"{url}/jobs/{job['id']}")
            if status == 200 and state.get("state") in ("done", "failed"):
                break
            if status not in (200, *RETRY):
                die(f"GET /jobs/{job['id'][:12]}: HTTP {status} {state.get('error', '')}")
            if time.monotonic() > stop:
                die(f"job {job['id'][:12]} still {state.get('state')} after {deadline:.0f} s; run again to resume it")
            time.sleep(poll)
        failed = []
        # keep every finished sentence, even when others failed: a rerun then asks only for the rest
        for it in state.get("items", []):
            text = batch[it["index"]][1][0]
            if it.get("state") != "done" or not it.get("url"):
                failed.append(text)
                continue
            if m := re.search(r"voicevox-(\d+\.\d+\.\d+)", it.get("key") or ""):
                JOBS_SEEN["version"] = m[1]
            try:
                data = http_bytes(it["url"])
                validate_wav(data)
            except (wave.Error, EOFError, RuntimeError) as e:
                die(f"{text[:30]!r}: {e}")
            write_atomic(batch[it["index"]][0], data)
        if failed:
            die(f"{len(failed)} sentences failed, e.g. {failed[0][:30]!r}; run again to retry only those")


def write_atomic(path: Path, data: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.stem + ".", suffix=".wav", delete=False) as f:
        tmp = Path(f.name)
        f.write(data)
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


# ---------- speakers ----------

def list_speakers() -> list[dict]:
    """The engine's speakers: [{name, styles: [{name, id, type}], credit}], only YES's voices for VOICEVOX."""
    b = backend()
    if b["kind"] == "files":
        path = os.environ.get("YES_TTS_SPEAKERS")
        if not path:
            raise RuntimeError("YES_TTS_FILES needs YES_TTS_SPEAKERS, the engine's speaker list as JSON")
        result = json.loads(Path(path).read_text())
    elif b["kind"] == "jobs":
        result = jobs_speakers(b["url"])
    else:
        r = run_tts([*tts_cmd(), "--list-speakers", "--json"])
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or f"exit {r.returncode}")
        result = json.loads(r.stdout)
    if licensed():
        result = [sp for sp in result if sp["name"] in SUPPORTED_VOICES]
        for speaker in result:
            speaker.update(voice_policy(speaker["name"]))
    return result


def style_ids(speakers: list[dict]) -> dict[tuple[str, str], int]:
    return {(sp["name"], st["name"]): st["id"]
            for sp in speakers for st in sp["styles"] if st.get("type", "talk") == "talk"}


def resolve(cast: list[dict], lines: list[dict], errors) -> list[dict]:
    """Give each line its style id and return the engine's speakers (none for the local single narrator).
    `errors(lines, cast, styles)` lists what is wrong with the cast's lines; any error stops."""
    if not cast and not names_narrator():
        return []
    try:
        speakers = list_speakers()
    except (OSError, RuntimeError, ValueError) as e:
        die(f"speaker list failed: {e}")
    styles = style_ids(speakers)
    if not cast:
        sid = styles.get(DEFAULT_NARRATOR)
        if sid is None:
            die("the speaker list has no ずんだもん ノーマル style")
        for ln in lines:
            ln["style_id"] = sid
        return speakers
    if errs := errors(lines, cast, styles):
        die("\n".join(errs))
    speaker_of = {m["id"]: m["speaker"] for m in cast}
    for ln in lines:
        ln["style_id"] = styles[(speaker_of[ln["who"]], ln["style"])]
    return speakers


def credit_of(speakers: list[dict]) -> dict[str, str]:
    return {sp["name"]: sp.get("credit") or f"VOICEVOX:{sp['name']}" for sp in speakers}


# ---------- synthesis ----------

def cache_key(said: str, speed: float, style_id: int | None) -> str:
    """(voice, speed, spoken text) plus the source, so audio from one engine never stands in for another."""
    src = f"{speed}|{said}" if style_id is None else f"{style_id}|{speed}|{said}"
    src = "yes-voicevox-0.25.2|" + backend()["id"] + "|" + src
    return hashlib.sha1(src.encode()).hexdigest()[:16]


def synth_jobs(lines: list[dict], readings: dict, cache: Path, speed: float) -> dict[str, tuple[str, int | None, Path]]:
    jobs = {}
    for ln in lines:
        said = spoken(ln, readings)
        style_id = ln.get("style_id")
        jobs[ln["id"]] = (said, style_id, cache / f"{cache_key(said, speed, style_id)}.wav")
    return jobs


def synth(lines: list[dict], readings: dict, cache: Path, speed: float) -> dict[str, Path]:
    """Every line's WAV, synthesizing only sentences the cache does not hold yet."""
    cache.mkdir(parents=True, exist_ok=True)
    jobs = synth_jobs(lines, readings, cache, speed)
    todo = {p: (s, sid) for s, sid, p in jobs.values() if not p.exists()}
    print(f"synth: {len(jobs)} lines, {len(todo)} new")
    b = backend()
    if b["kind"] == "files":
        if todo:
            die(f"{len(todo)} sentences have no audio yet: run `tts-plan <project>`, write each listed WAV, then build again.")
        return {lid: p for lid, (_, _, p) in jobs.items()}
    if b["kind"] == "jobs":
        if todo:
            jobs_synth(b["url"], todo, speed)
        return {lid: p for lid, (_, _, p) in jobs.items()}
    tts = tts_cmd()

    def run(item):
        path, (said, style_id) = item
        with tempfile.NamedTemporaryFile(dir=cache, prefix=path.stem + ".", suffix=".wav", delete=False) as file:
            tmp = Path(file.name)
        try:
            cmd = [*tts, "--text", said, "-o", str(tmp), "--force", "--speed", str(speed)]
            if style_id is not None:
                cmd += ["--speaker", str(style_id)]
            r = run_tts(cmd)
            if r.returncode != 0:
                return f"{said[:30]}…: {r.stderr.strip()}"
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


def tts_plan(lines: list[dict], readings: dict, cache: Path, speed: float, speaker_of: dict[str, str]) -> dict:
    """Every sentence without audio yet, with the file the build will read it from (YES_TTS_FILES)."""
    cache.mkdir(parents=True, exist_ok=True)
    jobs = synth_jobs(lines, readings, cache, speed)
    narrator = DEFAULT_NARRATOR[0] if licensed() else None
    items, seen = [], set()
    for ln in lines:
        said, style_id, path = jobs[ln["id"]]
        if path.exists() or path in seen:
            continue
        seen.add(path)
        items.append({"file": str(path), "text": said, "speaker": speaker_of.get(ln.get("who"), narrator),
                      "style": ln.get("style", "ノーマル"), "style_id": style_id, "speed": speed})
    return {"engine": backend()["engine"], "format": "WAV, 24000 Hz, mono, 16-bit", "items": items}


def engine_version() -> str | None:
    """The engine's version where it can be known: the pinned bundled engine, GET /version of
    YES_VOICEVOX_URL, or the version a jobs API put in its artifact keys during this run."""
    b = backend()
    if b["kind"] == "jobs":
        return JOBS_SEEN.get("version")
    if b["kind"] == "bundled" and not b["url"]:
        return PINNED_ENGINE
    if b["kind"] == "bundled":
        try:
            status, body = http_json(b["url"] + "/version", timeout=10)
        except (OSError, ValueError):
            return None
        return body if status == 200 and isinstance(body, str) else None
    return None
