import importlib.util
import http.client
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('yes_speak', ROOT/'plugins/yes/scripts/yes_speak.py')
speak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(speak)


def info(running=True, label='yes-speak', ip='127.0.0.1'):
    return {'Config':{'Image':speak.IMAGE,'Labels':{speak.LABEL:label}}, 'State':{'Running':running},
            'NetworkSettings':{'Ports':{'50021/tcp':[{'HostIp':ip,'HostPort':'51021'}]}}}


def wav_bytes():
    out=io.BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b'\0\0'*2400)
    return out.getvalue()


class DockerTests(unittest.TestCase):
    @patch.object(speak,'wait_ready')
    @patch.object(speak,'docker')
    @patch.object(speak,'inspect_container')
    def test_first_run_reuses_loopback_container(self, inspect, docker, ready):
        inspect.side_effect=[None,info()]
        docker.return_value=subprocess.CompletedProcess([],0,'id','')
        self.assertEqual(speak.ensure_engine(), 'http://127.0.0.1:51021')
        args=docker.call_args.args
        self.assertEqual(args[0],'run')
        self.assertIn('127.0.0.1::50021',args)
        self.assertIn(speak.IMAGE,args)
        ready.assert_called_once()

    @patch.object(speak,'wait_ready')
    @patch.object(speak,'docker')
    @patch.object(speak,'inspect_container',return_value=info())
    def test_running_container_is_not_restarted(self, inspect,docker,ready):
        speak.ensure_engine()
        docker.assert_not_called()

    @patch.object(speak,'wait_ready')
    @patch.object(speak,'docker')
    @patch.object(speak,'inspect_container',side_effect=[info(False),info()])
    def test_stopped_container_is_started(self, inspect,docker,ready):
        speak.ensure_engine()
        docker.assert_called_once_with('start',speak.CONTAINER,check=False)

    @patch.object(speak,'wait_ready')
    @patch.object(speak,'docker',return_value=subprocess.CompletedProcess([],1,'','already started'))
    @patch.object(speak,'inspect_container',side_effect=[info(False),info()])
    def test_concurrent_starter_is_reused(self,inspect,docker,ready):
        self.assertEqual(speak.ensure_engine(),'http://127.0.0.1:51021')
        ready.assert_called_once()

    @patch.object(speak,'wait_ready')
    @patch.object(speak,'docker',return_value=subprocess.CompletedProcess([],1,'','cannot start'))
    @patch.object(speak,'inspect_container',side_effect=[info(False),info(False)])
    def test_start_failure_is_reported(self,inspect,docker,ready):
        with self.assertRaisesRegex(speak.SpeakError,'cannot start'): speak.ensure_engine()
        ready.assert_not_called()

    @patch.object(speak,'wait_ready')
    @patch.object(speak,'docker',return_value=subprocess.CompletedProcess([],1,'','name already in use'))
    @patch.object(speak,'inspect_container',side_effect=[None,info()])
    def test_concurrent_creator_recovers_by_inspecting(self, inspect,docker,ready):
        self.assertEqual(speak.ensure_engine(),'http://127.0.0.1:51021')

    @patch.object(speak,'docker')
    @patch.object(speak,'inspect_container',return_value=info(label='someone-else'))
    def test_never_stops_unowned_container(self, inspect,docker):
        with self.assertRaises(speak.SpeakError): speak.stop_engine()
        docker.assert_not_called()

    def test_refuses_nonlocal_binding(self):
        with self.assertRaises(speak.SpeakError): speak.engine_url(info(ip='0.0.0.0'))

    @patch.object(speak,'request',return_value='0.0.0')
    def test_rejects_wrong_engine_version(self,request):
        with self.assertRaises(speak.SpeakError): speak.wait_ready('http://localhost',1)

    @patch.object(speak,'request',side_effect=speak.SpeakError('not ready'))
    @patch.object(speak.time,'monotonic',side_effect=[0,5])
    def test_readiness_timeout_is_bounded(self,clock,request):
        with self.assertRaisesRegex(speak.SpeakError,'did not become ready'): speak.wait_ready('http://localhost',1)

    @patch.object(speak.urllib.request.OpenerDirector,'open',side_effect=http.client.RemoteDisconnected('warming up'))
    def test_disconnected_engine_is_retryable(self,open_):
        with self.assertRaisesRegex(speak.SpeakError,'request failed'): speak.request('http://127.0.0.1:51021/version')

    @patch.object(speak.urllib.request.OpenerDirector,'open',side_effect=ConnectionResetError(104,'Connection reset by peer'))
    def test_connection_reset_is_retryable_during_readiness(self,open_):
        with self.assertRaisesRegex(speak.SpeakError,'request failed'):
            speak.request('http://127.0.0.1:51021/version')

    @patch.object(speak.time,'sleep')
    @patch.object(speak.urllib.request.OpenerDirector,'open',side_effect=[
        ConnectionResetError(104,'Connection reset by peer'), io.BytesIO(json.dumps(speak.VERSION).encode())])
    def test_readiness_recovers_after_connection_reset(self,open_,sleep):
        speak.wait_ready('http://127.0.0.1:51021',1)
        self.assertEqual(open_.call_count,2)
        sleep.assert_called_once_with(0.5)


class SynthesisTests(unittest.TestCase):
    @patch.object(speak, "request")
    def test_only_supported_voices_are_listed_or_resolved(self, request):
        request.return_value = [{"name": name, "styles": [{"id": i, "name": "ノーマル"}]}
                                for i, name in enumerate(["ずんだもん", "四国めたん", "春日部つむぎ"])]
        voices = speak.speakers("http://localhost")
        self.assertEqual([v["name"] for v in voices], ["ずんだもん", "四国めたん"])
        self.assertEqual([v["credit"] for v in voices], ["VOICEVOX:ずんだもん", "VOICEVOX:四国めたん"])
        self.assertTrue(all(v["terms_url"] == "https://zunko.jp/con_ongen_kiyaku.html" for v in voices))
        for value in ("春日部つむぎ", "2"):
            with self.assertRaises(speak.SpeakError):
                speak.resolve_speaker(value, voices)

    @patch.object(speak, 'synthesize', return_value=wav_bytes())
    @patch.object(speak, 'request', return_value=[{'name': '四国めたん', 'styles': [{'id': 2, 'name': 'ノーマル'}]}])
    @patch.object(speak, 'ensure_engine', return_value='http://localhost')
    def test_wav_has_notice_and_existing_notice_is_protected(self, engine, request, synth):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'speech.wav'
            notice = Path(str(path) + '.license.txt')
            args = ['hello', '--speaker', '2', '-o', str(path)]
            self.assertEqual(speak.main(args), 0)
            self.assertEqual(path.read_bytes(), wav_bytes())
            self.assertIn('VOICEVOX:四国めたん', notice.read_text())
            self.assertIn('zunko.jp/con_ongen_kiyaku.html', notice.read_text())
            self.assertIn('引継ぎ', notice.read_text())
            path.unlink()
            notice.write_text('original')
            engine.reset_mock()
            self.assertEqual(speak.main(args), 1)
            engine.assert_not_called()
            self.assertEqual(notice.read_text(), 'original')
            self.assertEqual(speak.main(args + ['--force']), 0)
            self.assertIn('VOICEVOX:四国めたん', notice.read_text())

    def test_resolves_names_and_styles(self):
        available=[{'name':'ずんだもん','credit':'VOICEVOX:ずんだもん','styles':[{'id':3,'name':'ノーマル'}]}]
        self.assertEqual(speak.resolve_speaker('ずんだもん',available),(3,'VOICEVOX:ずんだもん'))
        self.assertEqual(speak.resolve_speaker('3',available)[0],3)
        with self.assertRaises(speak.SpeakError): speak.resolve_speaker('unknown',available)

    @patch.object(speak, 'synthesize')
    @patch.object(speak, 'request', return_value=[{'name': '春日部つむぎ', 'styles': [{'id': 8, 'name': 'ノーマル'}]}])
    @patch.object(speak, 'ensure_engine', return_value='http://localhost')
    def test_unsupported_names_and_ids_never_synthesize(self, engine, request, synth):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'speech.wav'
            for name in ('春日部つむぎ', '8'):
                self.assertEqual(speak.main(['hello', '--speaker', name, '-o', str(output)]), 1)
            synth.assert_not_called()
            self.assertEqual(list(Path(folder).iterdir()), [])

    @patch.object(speak,'request')
    def test_synthesis_sets_speed_and_pcm_contract(self,request):
        request.side_effect=[{'speedScale':1},wav_bytes()]
        speak.synthesize('http://localhost','こんにちは & hello',3,1.25)
        self.assertIn('%26',request.call_args_list[0].args[0])
        self.assertEqual(request.call_args_list[1].args[2],{'speedScale':1.25,'outputSamplingRate':24000,'outputStereo':False})

    def test_corrupt_audio_is_rejected_and_existing_output_preserved(self):
        with self.assertRaises(speak.SpeakError): speak.validate_wav(b'not wav')
        with self.assertRaises(speak.SpeakError): speak.validate_wav(wav_bytes()[:-100])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'voice.wav'; p.write_bytes(b'original')
            with self.assertRaises(FileExistsError): speak.save_audio(p,wav_bytes(),False)
            self.assertEqual(p.read_bytes(),b'original')
            speak.save_audio(p,wav_bytes(),True)
            speak.validate_wav(p.read_bytes())

    @patch.object(speak,'ensure_engine')
    def test_invalid_input_never_starts_docker(self,engine):
        self.assertEqual(speak.main(['--text','hello','-o','x.wav','--speed','nan']),1)
        self.assertEqual(speak.main(['--text','','-o','x.wav']),1)
        engine.assert_not_called()


if __name__=='__main__': unittest.main()
