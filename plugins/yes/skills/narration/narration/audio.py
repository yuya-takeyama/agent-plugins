"""WAV in and out: joining lines with pauses, loudness and silence checks, BGM, m4a and mp3.

VOICEVOX writes 24000 Hz mono 16-bit; every line is read at that format and joined as raw PCM,
so a timeline's numbers are exact sample counts. ffmpeg (imageio-ffmpeg) does the encoding.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path
from typing import Callable

from . import die

RATE = 24000
LEAD_IN = 0.4
LOUDNESS = {"I": -16, "TP": -1.5, "LRA": 11}  # EBU R128 integrated, true peak, range


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path)) as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (RATE, 1, 2):
            die(f"{path}: expected {RATE}Hz mono 16-bit")
        return w.readframes(w.getnframes())


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(pcm))


def seconds(pcm: bytes) -> float:
    return len(pcm) / 2 / RATE


def concat(lines: list[dict], wavs: dict[str, Path], out_wav: Path, lead_in: float = LEAD_IN,
           extra: Callable[[dict, bytes], dict] | None = None) -> list[dict]:
    """Lead-in silence, then each line followed by its `pause`. Returns the lines with start and end."""
    pcm = bytearray(b"\0\0" * int(lead_in * RATE))
    timed = []
    for ln in lines:
        data = read_pcm(wavs[ln["id"]])
        start = len(pcm) / 2 / RATE
        pcm += data
        end = len(pcm) / 2 / RATE
        pcm += b"\0\0" * int(ln["pause"] * RATE)
        item = {**ln, "start": round(start, 3), "end": round(end, 3)}
        if extra:
            item.update(extra(ln, data))
        timed.append(item)
    write_wav(out_wav, pcm)
    return timed


def samples(pcm: bytes) -> array:
    s = array("h", pcm)
    if sys.byteorder == "big":
        s.byteswap()
    return s


# ---------- measurement ----------

SILENCE_DB = -50.0  # a 10 ms frame quieter than this is silence
FRAME = RATE // 100


def db(x: float) -> float:
    return 20 * math.log10(x / 32768) if x > 0 else -120.0


def measure(pcm: bytes) -> dict:
    """Peak and RMS (dBFS over voiced frames), leading and trailing silence, and the longest pause inside."""
    s = samples(pcm)
    frames = [s[i:i + FRAME] for i in range(0, len(s), FRAME)] or [array("h")]
    rms = [math.sqrt(sum(v * v for v in f) / len(f)) if len(f) else 0.0 for f in frames]
    quiet = [db(r) < SILENCE_DB for r in rms]
    voiced = [r for r, q in zip(rms, quiet) if not q]
    lead = next((i for i, q in enumerate(quiet) if not q), len(quiet))
    tail = next((i for i, q in enumerate(reversed(quiet)) if not q), len(quiet))
    longest = run = 0
    for q in quiet[lead:len(quiet) - tail]:
        run = run + 1 if q else 0
        longest = max(longest, run)
    peak = max((abs(v) for v in s), default=0)
    return {
        "seconds": round(len(s) / RATE, 3),
        "peak_db": round(db(peak), 1),
        "rms_db": round(db(math.sqrt(sum(r * r for r in voiced) / len(voiced))) if voiced else -120.0, 1),
        "lead": round(lead * FRAME / RATE, 2),
        "tail": round(tail * FRAME / RATE, 2),
        "gap": round(longest * FRAME / RATE, 2),
    }


GAP_WARN = 0.7  # a pause this long inside one line is usually a space, a symbol or a misreading
EDGE_WARN = 0.5
LEVEL_WARN = 6.0  # dB away from the median line


def level_warnings(stats: dict[str, dict]) -> list[str]:
    """Lines whose audio needs a listen: silent, clipped, a long pause inside, long edges, or out of level."""
    warns = []
    levels = sorted(s["rms_db"] for s in stats.values() if s["rms_db"] > -120)
    median = levels[len(levels) // 2] if levels else None
    for lid, s in stats.items():
        if s["rms_db"] <= -120:
            warns.append(f"{lid}: silent audio")
            continue
        if s["peak_db"] >= -0.1:
            warns.append(f"{lid}: clipped (peak {s['peak_db']} dBFS)")
        if s["gap"] >= GAP_WARN:
            warns.append(f"{lid}: {s['gap']} s of silence inside the line — a space, symbol or misreading? listen")
        if max(s["lead"], s["tail"]) >= EDGE_WARN:
            warns.append(f"{lid}: {s['lead']} s silence before, {s['tail']} s after the voice")
        if median is not None and abs(s["rms_db"] - median) >= LEVEL_WARN:
            warns.append(f"{lid}: {s['rms_db'] - median:+.1f} dB from the median line (a whisper style is expected to be quieter)")
    return warns


# ---------- encoding ----------

def loudnorm_filter(src: Path) -> str:
    """Two-pass EBU R128: measure `src`, then the linear loudnorm filter for it."""
    target = f"I={LOUDNESS['I']}:TP={LOUDNESS['TP']}:LRA={LOUDNESS['LRA']}"
    probe = subprocess.run(
        [ffmpeg(), "-hide_banner", "-i", str(src), "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    m = json.loads(probe[probe.rindex("{"):probe.rindex("}") + 1])
    return (
        f"loudnorm={target}:linear=true"
        f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
        f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}"
    )


def encode(raw_wav: Path, out_m4a: Path, bitrate: str) -> None:
    """The video player's track: loudness-normalized AAC at the voice's own 24 kHz mono."""
    af = loudnorm_filter(raw_wav)
    subprocess.run(
        [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_wav), "-af", af,
         "-ar", str(RATE), "-ac", "1", "-c:a", "aac", "-b:a", bitrate, str(out_m4a)],
        check=True,
    )


def mix_bgm(voice_wav: Path, bgm: Path, out_wav: Path, *, gain_db: float = -24, duck: bool = True,
            fade: float = 3.0) -> None:
    """Voice over looped music: the music at `gain_db`, ducked under speech, faded out at the end."""
    with wave.open(str(voice_wav)) as w:
        total = w.getnframes() / w.getframerate()
    bg = (f"[1:a]aresample={RATE},aformat=channel_layouts=mono,volume={gain_db}dB,"
          f"atrim=0:{total:.3f},afade=t=out:st={max(0.0, total - fade):.3f}:d={fade}[bg]")
    if duck:
        graph = (f"{bg};[0:a]asplit=2[v][sc];[bg][sc]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=500[bd];"
                 "[v][bd]amix=inputs=2:duration=first:normalize=0[out]")
    else:
        graph = f"{bg};[0:a][bg]amix=inputs=2:duration=first:normalize=0[out]"
    subprocess.run(
        [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(voice_wav), "-stream_loop", "-1",
         "-i", str(bgm), "-filter_complex", graph, "-map", "[out]", "-ar", str(RATE), "-ac", "1",
         "-c:a", "pcm_s16le", str(out_wav)],
        check=True,
    )


FORMATS = {"m4a": ["-c:a", "aac"], "mp3": ["-c:a", "libmp3lame"]}


def chapters_metadata(title: str, chapters: list[dict], duration: float, artist: str = "") -> str:
    """FFMETADATA1 text with one [CHAPTER] per {title, start, end} (seconds)."""
    def esc(v: str) -> str:
        return "".join("\\" + c if c in "=;#\\\n" else c for c in v)

    out = [";FFMETADATA1", f"title={esc(title)}"]
    if artist:
        out.append(f"artist={esc(artist)}")
    for ch in chapters:
        out += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(ch['start'] * 1000)}",
                f"END={int(min(ch['end'], duration) * 1000)}", f"title={esc(ch['title'])}"]
    return "\n".join(out) + "\n"


def export(src_wav: Path, out: Path, fmt: str, bitrate: str, metadata: str | None = None,
           rate: int = 44100) -> None:
    """Loudness-normalized m4a or mp3 for listening apps, with chapters and tags from `metadata`."""
    if fmt not in FORMATS:
        die(f"format must be one of {', '.join(FORMATS)}")
    af = loudnorm_filter(src_wav)
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src_wav)]
        if metadata:
            meta = Path(tmp) / "meta.txt"
            meta.write_text(metadata)
            cmd += ["-i", str(meta), "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1"]
        cmd += ["-af", af, "-ar", str(rate), "-ac", "1", *FORMATS[fmt], "-b:a", bitrate]
        if fmt == "mp3":
            cmd += ["-id3v2_version", "3"]
        subprocess.run([*cmd, str(out)], check=True)


def probe_loudness(path: Path) -> float:
    """Integrated loudness (LUFS) of an encoded file."""
    err = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    tail = err[err.rindex("Summary:"):]
    return float(tail.split("I:")[1].split("LUFS")[0])
