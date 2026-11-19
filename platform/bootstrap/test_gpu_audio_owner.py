"""GPU startup accepts initialized audio, but not an unapproved driver."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('gpu_owner',Path(__file__).parent/'gpu_runtime/owner_session.py')
owner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)

class AudioOwnerTests(unittest.TestCase):
    def test_no_audio_driver_needs_no_audio_helper(self):
        with patch.object(owner.Path,'exists',return_value=False), patch.object(owner.subprocess,'run') as run:
            owner.check_audio_owner()
            run.assert_not_called()

    def test_loaded_driver_requires_boot_approval(self):
        with patch.object(owner.Path,'exists',return_value=True), patch.object(owner.subprocess,'run') as run:
            owner.check_audio_owner()
            run.assert_called_once_with(['/usr/local/sbin/n810-audio','pcm-status'],check=True)
            run.side_effect=subprocess.CalledProcessError(1,'pcm-status')
            with self.assertRaises(subprocess.CalledProcessError):owner.check_audio_owner()
