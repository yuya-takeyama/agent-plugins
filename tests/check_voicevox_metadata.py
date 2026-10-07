"""Verify license metadata against the real pinned engine in the integration job."""
import json
from pathlib import Path
import sys

voices = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
by_name = {voice["name"]: voice for voice in voices}
assert set(by_name) == {"ずんだもん", "四国めたん"}, set(by_name)
for name, voice in by_name.items():
    assert voice["credit"] == f"VOICEVOX:{name}"
    assert voice["terms_url"] == "https://zunko.jp/con_ongen_kiyaku.html"
    assert voice["styles"] and all(style["type"] == "talk" for style in voice["styles"])
notice = Path(sys.argv[2]).read_text(encoding="utf-8")
assert "VOICEVOX:ずんだもん" in notice and "引継ぎ" in notice
assert "https://zunko.jp/con_ongen_kiyaku.html" in notice
print(f"Verified credits/terms for {len(voices)} engine voices and the WAV companion notice")
