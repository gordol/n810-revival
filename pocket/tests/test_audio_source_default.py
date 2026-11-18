import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from audio_monitor import default_socket,PCMSource
class SourceDefaults(unittest.TestCase):
    def test_unconfigured_source_does_not_retry_trial_socket(self):
        with patch.dict('os.environ',{},clear=True):
            source=PCMSource(default_socket())
            with patch('audio_monitor.socket.socket') as connect:
                source.poll();connect.assert_not_called()
            self.assertEqual(source.error,'No audio source configured')
    def test_explicit_environment_source_is_kept(self):
        with patch.dict('os.environ',{'N810_AUDIO_SOCKET':'/run/pocket-audio/pcm.sock'}):
            self.assertEqual(default_socket(),'/run/pocket-audio/pcm.sock')
