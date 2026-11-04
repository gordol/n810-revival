"""Optional native Mac audio output; explicit opt-in, bounded pipe, no audio files."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


class Playback:
    def __init__(self):
        self.enabled=False;self.child=None;self.build=None;self.directory=None;self.format=None;self.dropped=0
        self.available=sys.platform=='darwin' and Path(__file__).with_name('audio_output.c').is_file() and shutil.which('cc') is not None
        self.status='off' if self.available else 'unavailable on this host'
    def toggle(self):
        if not self.available:return
        if self.enabled:self.enabled=False;self.stop();self.status='off';return
        self.enabled=True
        if self.directory is None:
            self.directory=tempfile.TemporaryDirectory(prefix='cw-audio-output-')
            self.build=subprocess.Popen(['cc','-std=c11','-O2',str(Path(__file__).with_name('audio_output.c')),'-framework','AudioToolbox','-framework','CoreFoundation','-o',str(Path(self.directory.name)/'output')],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.status='preparing'
        else:self.status='waiting for PCM'
    def poll(self):
        if self.build and self.build.poll() is not None:
            code=self.build.returncode;self.build=None
            if code:self.enabled=False;self.available=False;self.status='build unavailable'
            else:self.status='waiting for PCM' if self.enabled else 'off'
        if self.child and self.child.poll() is not None:
            self.child.stdin.close();self.child=None;self.enabled=False;self.status='output unavailable'
    def stop(self):
        if self.child:
            child=self.child;self.child=None;child.stdin.close();child.terminate()
            try:child.wait(timeout=.2)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        self.format=None
        if self.enabled:self.status='waiting for PCM'
    def write(self,raw,fmt):
        if not self.enabled or self.build or not self.directory:return
        signature=(fmt['sample_rate'],fmt['channels'])
        if signature!=self.format:self.stop()
        if self.child is None:
            self.child=subprocess.Popen([str(Path(self.directory.name)/'output'),str(signature[0]),str(signature[1])],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            os.set_blocking(self.child.stdin.fileno(),False);self.format=signature
        try:
            if os.write(self.child.stdin.fileno(),raw)!=len(raw):raise BlockingIOError('Partial PCM write')
            self.status='on'
        except OSError:
            self.dropped+=1;self.stop();self.enabled=False;self.status='stopped: output backpressure'
    def close(self):
        self.enabled=False;self.stop()
        if self.build:
            self.build.terminate();self.build.wait();self.build=None
        if self.directory:self.directory.cleanup();self.directory=None
