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


class SynthesisTests(unittest.TestCase):
    def test_resolves_names_and_styles(self):
        available=[{'name':'ずんだもん','credit':'VOICEVOX:ずんだもん','styles':[{'id':3,'name':'ノーマル'}]}]
        self.assertEqual(speak.resolve_speaker('ずんだもん',available),(3,'VOICEVOX:ずんだもん'))
        self.assertEqual(speak.resolve_speaker('3',available)[0],3)
        with self.assertRaises(speak.SpeakError): speak.resolve_speaker('unknown',available)

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
