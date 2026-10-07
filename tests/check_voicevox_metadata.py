"""Verify license metadata against the real pinned engine in the integration job."""
import json
from pathlib import Path
import sys

voices = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
by_name = {voice["name"]: voice for voice in voices}
assert voices and all(voice["credit_verified"] for voice in voices), "Unmapped engine voice"
for name, credit in {
    "もち子さん": "VOICEVOX:もち子(cv 明日葉よもぎ)",
    "Voidoll": "VOICEVOX:Voidoll(CV:丹下桜)",
    "ユーレイちゃん": "VOICEVOX:ユーレイちゃん(CV:神崎零)",
    "里石ユカ": "VOICEVOX:里石ユカ（つぼみ）",
}.items():
    assert by_name[name]["credit"] == credit, (name, by_name[name]["credit"])
assert all(voice["terms_url"].startswith(("http://", "https://")) for voice in voices)
notice = Path(sys.argv[2]).read_text(encoding="utf-8")
assert "VOICEVOX:ずんだもん" in notice and "引継ぎ" in notice
assert "https://zunko.jp/con_ongen_kiyaku.html" in notice
print(f"Verified credits/terms for {len(voices)} engine voices and the WAV companion notice")
