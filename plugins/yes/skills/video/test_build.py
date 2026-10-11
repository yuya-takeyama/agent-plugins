# /// script
# requires-python = ">=3.11"
# dependencies = ["budoux>=0.6", "imageio-ffmpeg>=0.5", "playwright>=1.50", "fonttools>=4.50", "brotli>=1.1"]
# ///
"""uv run test_build.py"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import concurrent.futures as cf
import struct
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("build", HERE / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

SPEAKERS = [
    {"name": "四国めたん", "styles": [{"name": "ノーマル", "id": 2, "type": "talk"}, {"name": "ツンツン", "id": 6, "type": "talk"},
                                  {"name": "ノーマル", "id": 3002, "type": "sing"}], "credit": "VOICEVOX:四国めたん"},
    {"name": "ずんだもん", "styles": [{"name": "ノーマル", "id": 3, "type": "talk"}], "credit": "VOICEVOX:ずんだもん"},
]

FAKE_TTS = textwrap.dedent(f"""\
    #!{sys.executable}
    import json, os, sys, wave
    with open(os.environ["FAKE_TTS_LOG"], "a") as f:
        f.write(json.dumps(sys.argv[1:]) + "\\n")
    if "--list-speakers" in sys.argv:
        print({json.dumps(json.dumps(SPEAKERS))})
        sys.exit(0)
    with wave.open(sys.argv[sys.argv.index("-o") + 1], "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\\0\\0" * 2400)
""")


def pcm(*segments: tuple[float, int]) -> bytes:
    """(seconds, amplitude) segments of a 220 Hz tone; amplitude 0 is silence."""
    out: list[int] = []
    for sec, amp in segments:
        out += [int(amp * math.sin(2 * math.pi * 220 * t / build.RATE)) for t in range(round(sec * build.RATE))]
    return struct.pack(f"<{len(out)}h", *out)


def frame(n: int) -> float:
    return n / build.MOUTH_FPS


class ScenesHtmlTest(unittest.TestCase):
    def test_lone_data_out_gets_data_at_zero(self):
        self.assertEqual(
            build.out_implies_at('<div class="a" data-out="4"><p data-at="2" data-out="3">x</p><span>y</span></div>'),
            '<div class="a" data-at="0" data-out="4"><p data-at="2" data-out="3">x</p><span>y</span></div>')


class UsageTermsTest(unittest.TestCase):
    def test_other_cast_voices_are_rejected_before_synthesis(self):
        with self.assertRaises(SystemExit):
            build.load_cast({'cast': [{'id': 'guest', 'speaker': '春日部つむぎ'}]})
        self.assertEqual(len(build.load_cast({'cast': ['zundamon', 'metan']})), 2)

    def test_default_narrator_includes_terms_without_extra_engine_call(self):
        with patch.dict(os.environ, {}, clear=True):
            terms = build.terms_for({}, [], [], [])
        self.assertIn('引継ぎ', terms['text'])
        self.assertIn('https://zunko.jp/con_ongen_kiyaku.html', [link['url'] for link in terms['links']])

    def test_dialogue_keeps_used_voice_and_art_terms(self):
        cast = [{'id': 'm', 'speaker': '四国めたん', 'char': {'source': {
            'url': 'https://example.com/art', 'credit': 'Artist',
            'terms': [{'title': 'Art terms', 'url': 'https://example.com/terms'}]}}}]
        voices = [{'name': name, **build.voice_policy(name)} for name in ['四国めたん', 'ずんだもん']]
        with patch.dict(os.environ, {}, clear=True):
            terms = build.terms_for({}, cast, [{'who': 'm'}], voices)
        urls = [link['url'] for link in terms['links']]
        self.assertIn('https://zunko.jp/con_ongen_kiyaku.html', urls)
        self.assertIn('https://example.com/art', urls)
        self.assertIn('https://example.com/terms', urls)
        self.assertEqual(urls.count('https://zunko.jp/con_ongen_kiyaku.html'), 1)

    def test_custom_adapter_is_not_assumed_to_be_voicevox(self):
        custom = {'text': 'Custom audio terms', 'links': [{'title': 'License', 'url': 'https://example.com/license'}]}
        with patch.dict(os.environ, {'EV_TTS_CMD': 'custom'}):
            self.assertEqual(build.terms_for({'usageTerms': custom}, [], [], []), custom)
            self.assertEqual(build.terms_for({}, [], [], []), {})
            for bad in (None, {'links': []}, {'text': 'Bad', 'links': [{'title': 'Bad', 'url': 'javascript:alert(1)'}]}):
                with self.assertRaises(SystemExit):
                    build.terms_for({'usageTerms': bad}, [], [], [])


class FlattenTest(unittest.TestCase):
    SCRIPT = {"chapters": [
        {"id": "c1", "title": "t", "scenes": [{"id": "s1", "lines": [
            "first",
            {"text": "z1", "who": "zun", "face": "troubled"},
            "z2",
            {"text": "m1", "who": "met", "style": "ツンツン"},
            {"text": "z3", "who": "zun"},
            {"text": "z4", "face": "smile"},
        ]}], "quiz": {"q": "q", "a": "a", "a_who": "zun"}},
        {"id": "c2", "title": "t2", "scenes": [{"id": "s2", "lines": ["after quiz", {"text": "m2", "who": "met"}]}]},
    ]}

    def test_defaults_and_stickiness(self):
        got = [(ln["text"], ln["who"], ln["style"], ln["face"]) for ln in build.flatten(self.SCRIPT, ["met", "zun"])]
        self.assertEqual(got, [
            ("first", "met", "ノーマル", "normal"),       # first cast member
            ("z1", "zun", "ノーマル", "troubled"),
            ("z2", "zun", "ノーマル", "troubled"),        # previous speaker, face sticks
            ("m1", "met", "ツンツン", "normal"),          # met's own face, style not sticky below
            ("z3", "zun", "ノーマル", "troubled"),        # zun's face survived met's line
            ("z4", "zun", "ノーマル", "smile"),
            ("q", "met", "ノーマル", "normal"),           # q_who defaults to the explainer
            ("a", "zun", "ノーマル", "smile"),
            ("after quiz", "zun", "ノーマル", "smile"),   # previous line's speaker carries over
            ("m2", "met", "ノーマル", "normal"),
        ])

    def test_no_cast_adds_nothing(self):
        for ln in build.flatten(self.SCRIPT):
            self.assertFalse({"who", "style", "face"} & ln.keys())


class MouthTest(unittest.TestCase):
    def test_silence_voice_silence(self):
        levels = build.mouth_levels(pcm((frame(5), 0), (frame(10), 12000), (frame(5), 0)))
        self.assertEqual(levels, [0] * 5 + [2] * 10 + [0] * 5)

    def test_single_loud_frame_is_not_a_blip(self):
        levels = build.mouth_levels(pcm((frame(6), 0), (frame(1), 12000), (frame(6), 0), (frame(6), 12000)))
        self.assertEqual(levels[:13], [0] * 13)

    def test_hysteresis_holds_level_near_threshold(self):
        # 0.45 and 0.40 of the reference sit between open's leave (0.38) and enter (0.5) levels
        segs = [(frame(4), 20000)] + [(frame(1), 9000 if i % 2 else 8000) for i in range(12)]
        levels = build.mouth_levels(pcm(*segs))
        self.assertEqual(levels, [2] * 16)

    def test_no_run_shorter_than_two_frames(self):
        segs = [(frame(1), a) for a in (0, 12000, 0, 3000, 12000, 0, 12000, 3000, 0, 0, 12000, 12000)]
        levels = build.mouth_levels(pcm(*segs))
        runs, prev = [], None
        for v in levels:
            if v == prev:
                runs[-1] += 1
            else:
                runs.append(1)
            prev = v
        self.assertTrue(all(n >= 2 for n in runs), levels)

    def test_all_silent(self):
        self.assertEqual(build.mouth_levels(pcm((frame(4), 0))), [0] * 4)


class VoiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        fake = self.tmp / "fake-tts"
        fake.write_text(FAKE_TTS)
        fake.chmod(0o755)
        self.log = self.tmp / "log"
        os.environ["EV_TTS_CMD"] = f"{fake}"
        os.environ["FAKE_TTS_LOG"] = str(self.log)

    def tearDown(self):
        os.environ.pop("EV_TTS_CMD")

    def calls(self) -> list[list[str]]:
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_cache_key(self):
        old = hashlib.sha1(("yes-voicevox-0.25.2|" + os.environ["EV_TTS_CMD"] + "|1.0|こんにちは").encode()).hexdigest()[:16]
        self.assertEqual(build.cache_key("こんにちは", 1.0, None), old)
        self.assertEqual(build.cache_key("こんにちは", 1.0, 3), hashlib.sha1(("yes-voicevox-0.25.2|" + os.environ["EV_TTS_CMD"] + "|3|1.0|こんにちは").encode()).hexdigest()[:16])
        self.assertNotEqual(build.cache_key("こんにちは", 1.0, 3), build.cache_key("こんにちは", 1.0, 2))

    def test_synth_without_cast_passes_no_speaker(self):
        lines = [{"id": "a.0", "text": "あ"}]
        build.synth(lines, {}, self.tmp / "cache", 1.0)
        (call,) = self.calls()
        self.assertNotIn("--speaker", call)
        self.assertNotIn("--list-speakers", call)

    def test_synth_with_style_passes_speaker(self):
        build.synth([{"id": "a.0", "text": "あ", "style_id": 6}], {}, self.tmp / "cache", 1.0)
        (call,) = self.calls()
        self.assertEqual(call[call.index("--speaker") + 1], "6")

    def test_concurrent_builds_use_distinct_temporary_files(self):
        barrier = threading.Barrier(2)
        outputs = []
        cache = self.tmp / "cache"
        lines = [{"id": "a.0", "text": "あ"}]

        def fake_run(cmd, **kwargs):
            output = Path(cmd[cmd.index("-o") + 1])
            outputs.append(output)
            barrier.wait(timeout=5)
            with wave.open(str(output), "wb") as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
                wav.writeframes(b"\0\0" * 2400)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch.object(build.subprocess, "run", side_effect=fake_run):
            with cf.ThreadPoolExecutor(max_workers=2) as pool:
                paths = list(pool.map(lambda _: build.synth(lines, {}, cache, 1.0)["a.0"], range(2)))
        self.assertEqual(len(set(outputs)), 2)
        self.assertEqual(paths[0], paths[1])
        self.assertTrue(paths[0].is_file())
        self.assertEqual(list(cache.iterdir()), [paths[0]])

    def test_single_narrator_credit(self):
        with patch.dict(os.environ, {"EV_TTS_CMD": ""}):
            self.assertEqual(build.narration_credit({}), "VOICEVOX:ずんだもん")
        self.assertEqual(build.narration_credit({"credit": " Other TTS:Alice "}), "Other TTS:Alice")
        with self.assertRaises(SystemExit):
            build.narration_credit({})

    def test_list_speakers_and_styles(self):
        styles = build.style_ids(build.list_speakers())
        self.assertEqual(styles[("四国めたん", "ツンツン")], 6)
        self.assertEqual(styles[("四国めたん", "ノーマル")], 2)  # the sing style 3002 is not a talk style

    def test_credits_order(self):
        cast = [{"id": "met", "speaker": "四国めたん", "char": {"source": {"credit": "立ち絵: 坂本アヒル"}}},
                {"id": "zun", "speaker": "ずんだもん", "char": {"source": {"credit": "立ち絵: 坂本アヒル"}}},
                {"id": "silent", "speaker": "ずんだもん"}]
        timed = [{"who": "zun"}, {"who": "met"}, {"who": "zun"}]
        self.assertEqual(build.credits_for(timed, cast, SPEAKERS),
                         ["VOICEVOX:ずんだもん", "VOICEVOX:四国めたん", "立ち絵: 坂本アヒル"])

    def test_source_errors(self):
        self.assertEqual(build.source_errors([{"title": "a", "url": "https://x"}]), [])
        self.assertEqual(len(build.source_errors([{"title": "", "url": "https://x"}, {"title": "b", "url": "ftp://x"}])), 2)
        self.assertEqual(len(build.source_errors({"title": "a"})), 1)
        for value in (None, 12, " "):
            self.assertTrue(build.source_errors([{"title": value, "url": "https://example.com"}]))
        for url in (None, "https://", "javascript:alert(1)", "/relative", "https://["):
            self.assertTrue(build.source_errors([{"title": "a", "url": url}]))
        self.assertTrue(build.source_errors([{"title": "a", "url": "https://example.com", "note": {}}]))

    def test_cast_errors(self):
        cast = [{"id": "met", "speaker": "四国めたん", "char": {"faces": {"normal": {}, "smile": {}}}},
                {"id": "unavailable", "speaker": "ずんだもん"}]
        styles = build.style_ids(SPEAKERS[:1])
        lines = [
            {"id": "ok", "who": "met", "style": "ツンツン", "face": "smile"},
            {"id": "who", "who": "nobody", "style": "ノーマル", "face": "normal"},
            {"id": "face", "who": "met", "style": "ノーマル", "face": "angry"},
            {"id": "style", "who": "met", "style": "セクシー", "face": "normal"},
            {"id": "speaker", "who": "unavailable", "style": "ノーマル", "face": "anything"},
        ]
        errs = build.cast_errors(lines, cast, styles)
        self.assertEqual([e.split(":")[0] for e in errs], ["who", "face", "style", "speaker"])
        self.assertEqual([e.split(":")[0] for e in build.cast_errors(lines, cast, None)], ["who", "face"])


class BackendTest(unittest.TestCase):
    """Which speech source is used, and whether VOICEVOX rules apply to it."""

    def env(self, **kw):
        base = {k: "" for k in ("YES_TTS_CMD", "EV_TTS_CMD", "YES_TTS_FILES", "YES_TTS_ENGINE", "YES_TTS_SPEAKERS")}
        return patch.dict(os.environ, {**base, **kw})

    def test_default_is_the_bundled_voicevox(self):
        with self.env():
            b = build.backend()
        self.assertEqual((b["kind"], b["engine"]), ("bundled", "voicevox"))

    def test_a_command_is_other_unless_declared_voicevox(self):
        with self.env(EV_TTS_CMD="tts"):
            self.assertEqual(build.backend()["engine"], "other")
        with self.env(YES_TTS_CMD="zundaspeak", YES_TTS_ENGINE="voicevox"):
            self.assertEqual((build.backend()["kind"], build.backend()["engine"]), ("cmd", "voicevox"))

    def test_invalid_combinations_stop(self):
        for kw in ({"YES_TTS_ENGINE": "nope"}, {"YES_TTS_FILES": "1"}, {"YES_TTS_FILES": "1", "YES_TTS_CMD": "x", "YES_TTS_ENGINE": "other"},
                   {"YES_TTS_ENGINE": "other"}):
            with self.env(**kw), self.assertRaises(SystemExit):
                build.backend()

    def test_voicevox_rules_follow_the_engine_not_the_command(self):
        guest = {"cast": [{"id": "guest", "speaker": "春日部つむぎ"}]}
        with self.env(YES_TTS_CMD="zundaspeak", YES_TTS_ENGINE="voicevox"), self.assertRaises(SystemExit):
            build.load_cast(guest)
        with self.env(YES_TTS_FILES="1", YES_TTS_ENGINE="voicevox"), self.assertRaises(SystemExit):
            build.load_cast(guest)
        with self.env(YES_TTS_CMD="other-tts", YES_TTS_ENGINE="other"):
            self.assertEqual(build.load_cast(guest)[0]["speaker"], "春日部つむぎ")

    def test_another_voicevox_gets_current_terms_and_the_required_credit(self):
        with self.env(YES_TTS_CMD="zundaspeak", YES_TTS_ENGINE="voicevox"):
            terms = build.terms_for({}, [], [], [])
            self.assertEqual(build.narration_credit({}), "VOICEVOX:ずんだもん")
        urls = [link["url"] for link in terms["links"]]
        self.assertIn("https://zunko.jp/con_ongen_kiyaku.html", urls)
        self.assertTrue(any("/blob/main/" in u for u in urls))
        self.assertFalse(any("0.25.2" in u for u in urls))

    def test_cache_identity_differs_per_backend(self):
        with self.env():
            bundled = build.cache_key("あ", 1.0, 3)
        with self.env(YES_TTS_CMD="zundaspeak", YES_TTS_ENGINE="voicevox"):
            cmd = build.cache_key("あ", 1.0, 3)
        with self.env(YES_TTS_FILES="1", YES_TTS_ENGINE="voicevox"):
            files = build.cache_key("あ", 1.0, 3)
        self.assertEqual(len({bundled, cmd, files}), 3)


class VoicevoxCommandTest(unittest.TestCase):
    """A VOICEVOX command (zundaspeak and the like): the narrator is named, never the command's default."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        fake = self.tmp / "fake-tts"
        fake.write_text(FAKE_TTS)
        fake.chmod(0o755)
        self.log = self.tmp / "log"
        self.patch = patch.dict(os.environ, {"YES_TTS_CMD": str(fake), "YES_TTS_ENGINE": "voicevox", "EV_TTS_CMD": "",
                                             "YES_TTS_FILES": "", "FAKE_TTS_LOG": str(self.log)})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_single_narrator_is_zundamon_by_style_id(self):
        lines = [{"id": "a.0", "text": "あ"}]
        speakers = build.resolve_voices([], lines)
        self.assertEqual(lines[0]["style_id"], 3)
        self.assertEqual(speakers[0]["terms_url"], "https://zunko.jp/con_ongen_kiyaku.html")


class FilesBackendTest(unittest.TestCase):
    """YES_TTS_FILES: the agent writes the WAVs that tts-plan lists; build never runs a command."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.project = self.tmp / "p"
        (self.project).mkdir()
        (self.project / "script.json").write_text(json.dumps({"title": "t", "chapters": [
            {"id": "c", "title": "c", "scenes": [{"id": "c-1", "lines": ["あいう。", "えお。"]}]}]}, ensure_ascii=False))
        self.patch = patch.dict(os.environ, {"YES_TTS_FILES": "1", "YES_TTS_ENGINE": "voicevox", "YES_TTS_CMD": "", "EV_TTS_CMD": ""})
        self.patch.start()
        self.cache = patch.object(build, "TTS_CACHE", self.tmp / "cache")
        self.cache.start()

    def tearDown(self):
        self.cache.stop()
        self.patch.stop()

    def test_plan_lists_missing_sentences_then_build_reads_them(self):
        build.cmd_tts_plan(self.project)
        plan = json.loads((self.project / "out" / "tts-plan.json").read_text())
        self.assertEqual(plan["engine"], "voicevox")
        self.assertEqual([(i["text"], i["speaker"], i["style"]) for i in plan["items"]],
                         [("あいう。", "ずんだもん", "ノーマル"), ("えお。", "ずんだもん", "ノーマル")])
        _, readings, _, lines = build.load_project(self.project)
        with self.assertRaises(SystemExit):
            build.synth(lines, readings, build.TTS_CACHE, 1.0)
        for item in plan["items"]:
            with wave.open(item["file"], "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\0\0" * 2400)
        wavs = build.synth(lines, readings, build.TTS_CACHE, 1.0)
        self.assertEqual(len(wavs), 2)
        build.cmd_tts_plan(self.project)
        self.assertEqual(json.loads((self.project / "out" / "tts-plan.json").read_text())["items"], [])

    def test_a_cast_needs_the_speaker_list(self):
        speakers = self.tmp / "speakers.json"
        speakers.write_text(json.dumps(SPEAKERS, ensure_ascii=False))
        cast = build.load_cast({"cast": [{"id": "m", "speaker": "四国めたん"}]})
        lines = [{"id": "a.0", "text": "あ", "who": "m", "style": "ツンツン", "face": "normal"}]
        with self.assertRaises(SystemExit):
            build.resolve_voices(cast, lines)
        with patch.dict(os.environ, {"YES_TTS_SPEAKERS": str(speakers)}):
            build.resolve_voices(cast, lines)
        self.assertEqual(lines[0]["style_id"], 6)


if __name__ == "__main__":
    unittest.main()
