# /// script
# requires-python = ">=3.11"
# dependencies = ["imageio-ffmpeg>=0.5"]
# ///
"""uv run test_narration.py"""

from __future__ import annotations

import contextlib
import http.server
import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import narrate  # noqa: E402
from narration import audio, manifest, voices  # noqa: E402
from narration import reading as rd  # noqa: E402
from narration import script as sc  # noqa: E402

FAKE = f"{sys.executable} {HERE / 'testdata' / 'fake_tts.py'}"
ENV_KEYS = ("YES_TTS_CMD", "EV_TTS_CMD", "YES_TTS_FILES", "YES_TTS_ENGINE", "YES_TTS_SPEAKERS",
            "YES_VOICEVOX_URL", "YES_VOICEVOX_API")


def setUpModule():
    # The developer's shell may pick a speech backend; every test starts from none.
    env = patch.dict(os.environ)
    env.start()
    unittest.addModuleCleanup(env.stop)
    for key in ENV_KEYS:
        os.environ.pop(key, None)


def tone(seconds: float, amp: int = 8000, freq: float = 220) -> bytes:
    n = round(seconds * audio.RATE)
    return struct.pack(f"<{n}h", *(int(amp * math.sin(2 * math.pi * freq * t / audio.RATE)) for t in range(n)))


def wav_bytes(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(audio.RATE); w.writeframes(pcm)
    return buf.getvalue()


def quiet(fn, *args, **kw):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        result = fn(*args, **kw)
    return result, out.getvalue()


class SharedCasesTest(unittest.TestCase):
    """rules/cases.json is the contract another engine checks itself against."""

    def test_cases(self):
        cases = json.loads((HERE / "rules" / "cases.json").read_text())["cases"]
        self.assertGreaterEqual(len(cases), 10)
        for case in cases:
            with self.subTest(case["name"]):
                said = rd.spoken(case["line"], case["readings"])
                self.assertEqual(said, case["spoken"])
                self.assertEqual(rd.unread_words(said), case["unread"])


class SeedDictionaryTest(unittest.TestCase):
    def test_every_seed_reading_is_speakable(self):
        seed = json.loads(rd.SEED.read_text())
        self.assertGreater(len(seed), 150)
        for surface, value in seed.items():
            with self.subTest(surface):
                self.assertNotRegex(value, r"[ 　A-Za-z]", "a reading is katakana or kana, joined")
                self.assertEqual(rd.spoken({"text": f"{surface} です"}, seed), f"{value}です")

    def test_project_readings_override_the_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "readings.json"
            path.write_text(json.dumps({"Go": "ゴーげんご"}))
            readings = rd.load_readings(path, {"Rust": "ラストげんご"})
        self.assertEqual(rd.spoken({"text": "Go と Rust と Python"}, readings), "ゴーげんごとラストげんごとパイソン")


class LintTest(unittest.TestCase):
    def test_line_checks(self):
        r = {"DB": "ディービー"}
        long = {"id": "long", "text": "あ" * 61}
        commas = {"id": "commas", "text": "前提は、有料の基盤、外部の DB、ドメインです。"}
        joined = {"id": "joined", "text": "前提は、有料の基盤、外部の DB、ドメインです。",
                  "reading": "前提は有料の基盤と外部のディービーとドメインです。"}
        unread = {"id": "unread", "text": "Spanner と TrueTime"}
        self.assertEqual([w.split(":")[0] for w in rd.line_warnings(long, r)], ["long"])
        self.assertIn("読点", rd.line_warnings(commas, r)[0])
        self.assertEqual(rd.line_warnings(joined, r), [])
        self.assertIn("Spanner, TrueTime", rd.line_warnings(unread, {})[0])
        self.assertIn("chars/s", rd.line_warnings({"id": "fast", "text": "あ" * 30}, {}, seconds=2.0)[0])
        self.assertEqual(rd.line_warnings({"id": "ok", "text": "あ" * 30}, {}, seconds=5.0), [])

    def test_spaces_that_would_have_paused_are_reported(self):
        lines = [{"id": "a", "text": "x", "say": "コミット ウェイト を待つ"},
                 {"id": "b", "text": "x", "reading": "Hello World"}]
        warns = rd.space_warnings(lines, {"commit wait": "コミット ウェイト", "Hello World": "ハローワールド"})
        self.assertEqual(len(warns), 2)
        self.assertIn("'コミットウェイト'", warns[0])
        self.assertTrue(warns[1].startswith("a: say"))

    def test_number_hints(self):
        flagged = ["3〜5人", "1/3です", "10:30に開始", "3x速い", "1920x1080", "v0.25.2"]
        plain = ["12000円", "2026年", "3倍速い", "約30%", "11月22日", "3から5人"]
        for text in flagged:
            self.assertTrue(rd.number_hints(text), text)
        for text in plain:
            self.assertEqual(rd.number_hints(text), [], text)


class ScriptTest(unittest.TestCase):
    SCRIPT = {"chapters": [
        {"id": "c1", "title": "一", "lines": [
            {"who": "z", "text": "z1"}, "z2", {"who": "m", "text": "m1"}, {"who": "z", "text": "z3", "pause": 0.8},
            {"who": "m", "text": "m2"}]},
        {"id": "c2", "title": "二", "scenes": [{"id": "s1", "lines": ["m3"]}, {"id": "s2", "lines": ["m4"]}],
         "quiz": {"q": "q", "a": "a", "a_who": "z"}},
    ]}

    def test_pauses_by_what_comes_next(self):
        lines = sc.flatten(self.SCRIPT, ["z", "m"], sc.pauses_for({"pauses": {"turn": 0.25}}))
        got = [(ln["id"], ln["who"], ln["pause"]) for ln in lines]
        self.assertEqual(got, [
            ("c1.0", "z", 0.35),   # same speaker next
            ("c1.1", "z", 0.25),   # turn
            ("c1.2", "m", 0.25),   # turn
            ("c1.3", "z", 0.8),    # the script's own pause wins over the turn
            ("c1.4", "m", 1.4),    # chapter end
            ("s1.0", "m", 0.9),    # scene end
            ("s2.0", "m", 0.9),    # the quiz scene follows, so a scene pause
            ("c2-quiz.0", "z", 4.0),
            ("c2-quiz.1", "z", 1.0),  # the end
        ])

    def test_turn_defaults_to_the_line_pause(self):
        self.assertEqual([ln["pause"] for ln in sc.flatten(self.SCRIPT, ["z", "m"])][:3], [0.35, 0.35, 0.35])

    def test_bad_pauses_stop(self):
        for bad in ({"gap": 1}, {"line": -1}, {"line": "1"}, "slow"):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                sc.pauses_for({"pauses": bad})

    def test_cast(self):
        cast = sc.load_cast({"cast": ["metan", {"id": "z", "speaker": "ずんだもん", "name": "ずん", "color": "#0a0"}]})
        self.assertEqual(cast, [{"id": "metan", "name": "四国めたん", "speaker": "四国めたん"},
                                {"id": "z", "name": "ずん", "speaker": "ずんだもん", "color": "#0a0"}])
        styles = {("四国めたん", "ノーマル"): 2}
        lines = [{"id": "a", "who": "metan", "style": "ノーマル"}, {"id": "b", "who": "x", "style": "ノーマル"},
                 {"id": "c", "who": "metan", "style": "セクシー"}]
        self.assertEqual([e.split(":")[0] for e in sc.check_cast(lines, cast, styles)], ["b", "c"])


class BackendTest(unittest.TestCase):
    def env(self, **kw):
        return patch.dict(os.environ, {**{k: "" for k in ENV_KEYS}, **kw})

    def test_engine_url_keeps_the_bundled_adapter_but_not_its_cache_or_pinned_terms(self):
        with self.env():
            local = voices.backend()
            self.assertTrue(voices.pinned())
            key_local = voices.cache_key("あ", 1.0, None)
        with self.env(YES_VOICEVOX_URL="http://engine.example:50021/"):
            other = voices.backend()
            self.assertFalse(voices.pinned())
            self.assertFalse(voices.names_narrator())
            key_other = voices.cache_key("あ", 1.0, None)
        self.assertEqual((local["kind"], other["kind"]), ("bundled", "bundled"))
        self.assertEqual(other["url"], "http://engine.example:50021")
        self.assertNotEqual(key_local, key_other)

    def test_jobs_api(self):
        with self.env(YES_VOICEVOX_URL="https://api.example", YES_VOICEVOX_API="jobs"):
            b = voices.backend()
            self.assertTrue(voices.names_narrator())
            self.assertTrue(voices.licensed())
        self.assertEqual((b["kind"], b["url"]), ("jobs", "https://api.example"))
        for kw in ({"YES_VOICEVOX_API": "jobs"}, {"YES_VOICEVOX_API": "soap", "YES_VOICEVOX_URL": "https://x"}):
            with self.env(**kw), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                voices.backend()

    def test_a_command_or_files_win_over_the_url(self):
        with self.env(YES_TTS_CMD="tts", YES_VOICEVOX_URL="https://x", YES_VOICEVOX_API="jobs"):
            self.assertEqual(voices.backend()["kind"], "cmd")


class FakeJobsAPI(http.server.BaseHTTPRequestHandler):
    """POST /jobs, GET /jobs/<id>, GET /speakers and the audio, as the jobs contract describes them."""
    jobs: dict = {}
    posts: list = []
    fail_first_post = False

    def log_message(self, *a):
        pass

    def reply(self, status, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/speakers":
            return self.reply(200, [{"name": "ずんだもん", "credit": "VOICEVOX:ずんだもん",
                                     "styles": [{"name": "ノーマル", "id": 3, "type": "talk"}]},
                                    {"name": "四国めたん", "credit": "VOICEVOX:四国めたん",
                                     "styles": [{"name": "ノーマル", "id": 2, "type": "talk"}]},
                                    {"name": "春日部つむぎ", "styles": [{"name": "ノーマル", "id": 8, "type": "talk"}]}])
        if m := re.fullmatch(r"/jobs/(\w+)", self.path):
            items = self.jobs[m[1]]
            base = f"http://{self.headers['Host']}"
            return self.reply(200, {"state": "done", "items": [
                {"index": i, "state": "done", "url": f"{base}/audio/{m[1]}/{i}", "credit": "VOICEVOX:ずんだもん"}
                for i in range(len(items))]})
        if m := re.fullmatch(r"/audio/(\w+)/(\d+)", self.path):
            item = self.jobs[m[1]][int(m[2])]
            return self.reply(200, wav_bytes(tone(0.05 * len(item["text"]))), "audio/wav")
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).posts.append(body)
        if type(self).fail_first_post:
            type(self).fail_first_post = False
            return self.reply(503, {"error": "Engine starting"})
        job = f"job{len(self.jobs)}"
        self.jobs[job] = body["items"]
        self.reply(202, {"id": job, "state": "queued", "total": len(body["items"]), "done": 0, "failed": 0})


class ProjectTest(unittest.TestCase):
    """The narrate.py commands on the bundled podcast example."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.project = self.tmp / "podcast"
        shutil.copytree(HERE / "example" / "podcast", self.project)
        cache = patch.object(voices, "TTS_CACHE", self.tmp / "cache")
        cache.start()
        self.addCleanup(cache.stop)

    def env(self, **kw):
        return patch.dict(os.environ, {**{k: "" for k in ENV_KEYS}, **kw})

    def test_build_writes_narration_json_and_a_chaptered_m4a_and_mp3(self):
        with self.env(YES_TTS_CMD=FAKE):
            m, out = quiet(narrate.cmd_synth, self.project)
            self.assertIn("8 new", out)
            self.assertEqual(quiet(narrate.cmd_check, self.project)[0], 0)
            target, _ = quiet(narrate.cmd_mix, self.project, "m4a", "64k")
            mp3, _ = quiet(narrate.cmd_mix, self.project, "mp3", "64k")
            _, again = quiet(narrate.cmd_synth, self.project)
        self.assertIn("8 lines, 0 new", again)
        saved = json.loads((self.project / "out" / "narration.json").read_text())
        self.assertEqual(saved["credits"], ["VOICEVOX:ずんだもん", "VOICEVOX:四国めたん"])
        self.assertEqual(saved["engine"], {"name": "VOICEVOX", "source": "cmd", "version": None})
        line = saved["lines"][6]
        self.assertEqual((line["who"], line["speaker"], line["spoken"], line["pause"], line["speed"]),
                         ("metan", "四国めたん", "だからティーティーエル、つまり結果の有効期限を決めて、古くなった結果は捨てるの。", 0.6, 1.05))
        self.assertEqual(line["sha256"], manifest.sha256(self.project / "out" / line["file"]))
        self.assertEqual([ln["pause"] for ln in saved["lines"]][:4], [0.3, 0.35, 0.3, 1.4])
        self.assertIn("引継ぎ", saved["usageTerms"]["text"])
        for path in (target, mp3):
            self.assertAlmostEqual(audio.probe_loudness(path), -16, delta=1.5)
            info = subprocess.run([audio.ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
            self.assertEqual(info.count("Chapter #"), 2, path)
            self.assertIn("なぜ速くなるのか", info)
        transcript = (self.project / "out" / "transcript.md").read_text()
        self.assertIn("ずんだもん: めたん、同じ計算", transcript)
        self.assertTrue(transcript.rstrip().endswith("VOICEVOX:四国めたん"))
        timeline = json.loads((self.project / "out" / "timeline.json").read_text())
        self.assertEqual(timeline["chapters"][0]["start"], 0.0)
        self.assertEqual(timeline["lines"][0]["start"], 0.4)
        self.assertIn("say:  だからティーティーエル、つまり", (self.project / "out" / "spoken.md").read_text())

    def test_only_changed_lines_are_synthesized_and_stale_audio_is_dropped(self):
        with self.env(YES_TTS_CMD=FAKE):
            quiet(narrate.cmd_synth, self.project)
            script = json.loads((self.project / "script.json").read_text())
            script["chapters"][0]["lines"][3]["text"] = "計算しないから、とても速いのだ！"
            (self.project / "script.json").write_text(json.dumps(script, ensure_ascii=False))
            _, out = quiet(narrate.cmd_synth, self.project)
        self.assertIn("8 lines, 1 new", out)
        self.assertEqual(len(list((self.project / "out" / "narration").glob("*.wav"))), 8)

    def test_bgm_is_ducked_under_speech(self):
        (self.project / "bgm.wav").write_bytes(wav_bytes(tone(2.0, 6000, 440)))
        script = json.loads((self.project / "script.json").read_text())
        script["bgm"] = {"file": "bgm.wav", "gain": -6}
        (self.project / "script.json").write_text(json.dumps(script, ensure_ascii=False))
        with self.env(YES_TTS_CMD=FAKE):
            quiet(narrate.cmd_synth, self.project)
            quiet(narrate.cmd_mix, self.project, "m4a", "64k")
        mixed = audio.read_pcm(self.project / "out" / "narration.mix.wav")
        raw = audio.read_pcm(self.project / "out" / "narration.raw.wav")
        self.assertEqual(len(mixed), len(raw))
        lead = audio.measure(mixed[:int(0.3 * audio.RATE) * 2])
        self.assertGreater(lead["rms_db"], -40, "music plays in the lead-in, longer than its 2 s file once looped")
        self.assertGreater(audio.measure(mixed[-int(6 * audio.RATE) * 2:-int(4 * audio.RATE) * 2])["rms_db"], -60)

    def test_jobs_api_synthesizes_missing_lines_in_one_job(self):
        FakeJobsAPI.jobs, FakeJobsAPI.posts, FakeJobsAPI.fail_first_post = {}, [], True
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeJobsAPI)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}"
        with self.env(YES_VOICEVOX_URL=url, YES_VOICEVOX_API="jobs"), \
                patch.object(voices.time, "sleep"), patch.dict(os.environ, {"NO_PROXY": "*"}):
            quiet(narrate.cmd_synth, self.project)
            quiet(narrate.cmd_synth, self.project)
        self.assertEqual(len(FakeJobsAPI.posts), 2, "one 503, then one job; the rerun posts nothing")
        items = FakeJobsAPI.posts[1]["items"]
        self.assertEqual(len(items), 8)
        self.assertEqual({(i["speaker"], i["speedScale"]) for i in items}, {(2, 1.05), (3, 1.05)})
        saved = json.loads((self.project / "out" / "narration.json").read_text())
        self.assertEqual(saved["engine"]["source"], "jobs")
        self.assertNotIn(url, json.dumps(saved), "narration.json never records the API address")

    def test_other_voices_are_refused(self):
        script = json.loads((self.project / "script.json").read_text())
        script["cast"] = [{"id": "t", "speaker": "春日部つむぎ"}]
        (self.project / "script.json").write_text(json.dumps(script, ensure_ascii=False))
        with self.env(YES_TTS_CMD=FAKE), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            narrate.load(self.project)

    def test_lint_and_spoken_on_a_video_project(self):
        video = HERE.parent / "zundamon-video" / "example"
        with self.env(YES_TTS_CMD=FAKE):
            code, out = quiet(narrate.cmd_lint, video)
        self.assertEqual(code, 0, out)
        self.assertIn("33 lines", out)
        shutil.copytree(video, self.tmp / "video")
        _, report = quiet(narrate.cmd_spoken, self.tmp / "video")
        self.assertIn("c1-1.0", report)

    def test_say(self):
        _, out = quiet(narrate.cmd_say, "TrueTime で 10GB を 1/3 にする", None)
        self.assertEqual(out.strip(), "トゥルータイムで10ギガバイトを1/3にする")


class AudioTest(unittest.TestCase):
    def test_measure_and_level_warnings(self):
        line = tone(0.1, 0, 220) + tone(0.5) + tone(0.8, 0) + tone(0.5) + tone(0.6, 0)
        s = audio.measure(line)
        self.assertEqual((s["lead"], s["tail"], s["gap"]), (0.1, 0.6, 0.8))
        stats = {"ok": audio.measure(tone(1.0)), "ok2": audio.measure(tone(1.0)), "gappy": s,
                 "quiet": audio.measure(tone(1.0, 1500)), "silent": audio.measure(tone(1.0, 0))}
        warns = audio.level_warnings(stats)
        self.assertEqual(sorted({w.split(":")[0] for w in warns}), ["gappy", "quiet", "silent"])
        self.assertTrue(any("inside the line" in w for w in warns))

    def test_concat_times_lines_by_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name, sec in (("a", 1.0), ("b", 0.5)):
                (tmp / f"{name}.wav").write_bytes(wav_bytes(tone(sec)))
            timed = audio.concat([{"id": "a", "pause": 0.3}, {"id": "b", "pause": 1.0}],
                                 {"a": tmp / "a.wav", "b": tmp / "b.wav"}, tmp / "out.wav")
            self.assertEqual([(t["start"], t["end"]) for t in timed], [(0.4, 1.4), (1.7, 2.2)])
            self.assertAlmostEqual(audio.seconds(audio.read_pcm(tmp / "out.wav")), 3.2, places=3)

    def test_chapter_metadata_escapes(self):
        meta = audio.chapters_metadata("a=b", [{"title": "x;y", "start": 0, "end": 2.5}], 2.0)
        self.assertIn("title=a\\=b", meta)
        self.assertIn("END=2000", meta)
        self.assertIn("title=x\\;y", meta)


if __name__ == "__main__":
    unittest.main()
