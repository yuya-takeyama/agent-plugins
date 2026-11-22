"""Deterministic stand-in for yes-speak: audio whose length and loudness follow the text.

The golden test (test_build.py GoldenTest) runs the build against it, so the
pinned timeline and mouth shapes depend only on the build, never on an engine."""
import json
import math
import struct
import sys
import wave

SPEAKERS = [
    {"name": "四国めたん", "credit": "VOICEVOX:四国めたん", "styles": [
        {"name": n, "id": i, "type": "talk"} for n, i in
        (("ノーマル", 2), ("あまあま", 0), ("ツンツン", 6), ("セクシー", 4), ("ささやき", 36), ("ヒソヒソ", 37))]},
    {"name": "ずんだもん", "credit": "VOICEVOX:ずんだもん", "styles": [
        {"name": n, "id": i, "type": "talk"} for n, i in
        (("ノーマル", 3), ("あまあま", 1), ("ツンツン", 7), ("セクシー", 5), ("ささやき", 22), ("ヒソヒソ", 38),
         ("ヘロヘロ", 75), ("なみだめ", 76))]},
]


def main(argv: list[str]) -> None:
    if "--list-speakers" in argv:
        print(json.dumps(SPEAKERS, ensure_ascii=False))
        return
    text = argv[argv.index("--text") + 1]
    out = argv[argv.index("-o") + 1]
    speed = float(argv[argv.index("--speed") + 1]) if "--speed" in argv else 1.0
    speaker = int(argv[argv.index("--speaker") + 1]) if "--speaker" in argv else 0
    rate, per_char = 24000, 0.06 / speed
    freq = 180 + 7 * speaker
    samples: list[int] = [0] * int(0.05 * rate)
    for ch in text:
        amp = 0 if ch in "、。！？ " else 2500 + (ord(ch) % 9) * 1500
        n = int(per_char * rate)
        start = len(samples)
        samples += [int(amp * math.sin(2 * math.pi * freq * (start + k) / rate)) for k in range(n)]
    samples += [0] * int(0.08 * rate)
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))


if __name__ == "__main__":
    main(sys.argv[1:])
