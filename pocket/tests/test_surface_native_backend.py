"""Backend selection must preserve the ordinary room and unsupported app paths."""
from pathlib import Path
import sys,unittest
from unittest.mock import patch
from dataclasses import replace
shell=Path(__file__).resolve().parents[1]/'shell'
sys.path[:0]=[str(shell/'apps/surface-renderer'),str(shell)]
from native_backend import NativeRoomBackend
from frame_job import Request
from surface_renderer import GlyphRenderer,ToneRenderer
from profiles import ROOM
from core import Host,Window
from app import SurfaceRoom

class NativeSelection(unittest.TestCase):
    def setUp(self):
        self.request=Request(80,22,80,22,0,0,-600,0,0,False,False,0,0)
        self.backend=NativeRoomBackend(['/must/not/start'])
        self.renderer=GlyphRenderer(max_cells=6000,max_glyphs=1600)
    def test_only_verified_contract_is_admitted_before_spawn(self):
        self.assertTrue(self.backend.supports(self.request,self.renderer,ROOM))
        for changes in ({'outdoors':True},{'portal':True},{'rift':True},{'width':101},{'height':31}):
            self.assertFalse(self.backend.supports(replace(self.request,**changes),self.renderer,ROOM))
        self.assertFalse(self.backend.supports(self.request,ToneRenderer(),ROOM))
        self.assertFalse(self.backend.supports(self.request,GlyphRenderer(),ROOM))
        self.assertFalse(self.backend.supports(self.request,self.renderer,{}))
        self.assertIsNone(self.backend.process)
    def test_app_keeps_fallback_and_routes_supported_work(self):
        host=Host(100,30,[Window('Surface room',2,2,82,24)])
        app=SurfaceRoom(host,frame_backend=self.backend,asynchronous=False)
        with patch('app.prepare',return_value='fallback') as legacy,patch.object(self.backend,'prepare',return_value='native') as native:
            self.assertEqual(app._prepare(self.request),'native');legacy.assert_not_called()
            self.assertEqual(app._prepare(replace(self.request,outdoors=True)),'fallback')
            self.assertEqual(native.call_count,1);self.assertEqual(legacy.call_count,1)
        app.close();self.assertTrue(self.backend.closed)

if __name__=='__main__':unittest.main()
