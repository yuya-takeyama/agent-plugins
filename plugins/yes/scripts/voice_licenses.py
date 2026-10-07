"""Credit and terms metadata for the pinned VOICEVOX engine, not a grant of rights."""
from __future__ import annotations

import json
from pathlib import Path

CATALOG = json.loads(Path(__file__).with_name("voicevox_voices.json").read_text(encoding="utf-8"))
ENGINE_TERMS = CATALOG["source"]
MODEL_TERMS = "https://github.com/VOICEVOX/voicevox_vvm/blob/0.16.4/README.md"
REUSE_NOTICE = (
    "YESのMITライセンスは音声・キャラクター・立ち絵には適用されません。"
    "音声の再利用は各音源の規約に従い、必要なクレジットを表示してください。"
    "音声の利用を他者に許諾する場合は、その相手にも各音源規約の遵守と、"
    "さらに他者へ許諾する際の同条件の引継ぎを義務付けてください。"
    "この表示自体は、音声や立ち絵の再利用を許諾するものではありません。"
)
REVIEW_NOTE = (
    "Check the current voice terms for your user type, purpose, and publication/distribution format. "
    "Credit alone does not establish permission."
)
SPECIAL_NOTES = {
    "青山龍星": "Companies, sole proprietors, and individuals contracted by companies need prior application and permission, even without revenue.",
    "もち子さん": "Corporate involvement, audio works/materials, games, and downloadable distributions have additional conditions; check the current terms.",
    "Voidoll": "Corporate use requires an individual inquiry under the pinned engine guidance.",
    "ユーレイちゃん": "Commercial uses beyond the specified doujin/streaming exceptions require prior confirmation.",
    "No.7": "Commercial uses beyond the specified doujin/streaming exceptions require prior confirmation.",
    "後鬼": "Corporate involvement requires prior confirmation under the pinned engine guidance.",
    "ぞん子": "Commercial use requires an individual inquiry under the pinned engine guidance.",
}


def voice_policy(name: str) -> dict:
    known = CATALOG["voices"].get(name)
    return {
        "credit": known["credit"] if known else f"VOICEVOX:{name}",
        "credit_verified": known is not None,
        "terms_url": known["terms_url"] if known else ENGINE_TERMS,
        "license_notes": [REVIEW_NOTE] + ([SPECIAL_NOTES[name]] if name in SPECIAL_NOTES else [])
        + ([] if known else ["Unlisted voice: verify both the required credit and voice-specific terms before use."]),
    }


def usage_notice(voices: list[dict], art: list[dict] = ()) -> dict:
    links = []
    if voices:
        links += [{"title": "VOICEVOX エンジン利用規約 (0.25.2)", "url": ENGINE_TERMS},
                  {"title": "VOICEVOX 音声モデル利用規約 (0.16.4)", "url": MODEL_TERMS}]
    for voice in voices:
        links.append({"title": f"{voice['name']} 音源利用規約", "url": voice["terms_url"],
                      "note": " ".join(voice.get("license_notes", []))})
    for source in art:
        for link in source.get("terms", []):
            if link not in links:
                links.append(link)
        if source.get("url"):
            links.append({"title": source.get("credit", "立ち絵") + " 配布元・同梱README", "url": source["url"]})
    return {"text": REUSE_NOTICE, "links": links}


def audio_notice(speaker: dict) -> str:
    notice = usage_notice([speaker])
    lines = [speaker["credit"], "", notice["text"], ""]
    for link in notice["links"]:
        lines += [f"{link['title']}: {link['url']}", link.get("note", "")]
    lines += ["Display the credit where listeners can find it. For audio-only distribution, "
              "include an appropriate spoken credit or accompanying accessible credit; a detached sidecar alone may not reach listeners."]
    return "\n".join(lines) + "\n"
