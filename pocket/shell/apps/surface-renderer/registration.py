"""Cheap registration; Runtime decides any canonical registry integration."""
from pathlib import Path
import importlib.util

def app_module():
    import sys
    directory=Path(__file__).resolve().parent
    if str(directory) not in sys.path:sys.path.insert(0,str(directory))
    spec=importlib.util.spec_from_file_location('_surface_room_app',directory/'app.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def create(host,**options):
    return app_module().SurfaceRoom(host,**options)


def descriptor():
    return dict(id='surface-room',title='Surface room',preferred_size=(82,29),minimum_size=(22,12),category='Experiments',
        description='Framework-native room with material-anchored glyph surfaces',
        help=(('Explore',('W/S walk; A/D strafe; arrows turn.','One moving object; isolated rendering proof.')),),factory=create)


def create_outdoors(host,**options):
    # The saved overview cameras belong to Scenery; expose that existing app
    # rather than creating another camera library in the walking demo.
    class RainierWalk(app_module().SurfaceRoom):
        def __init__(self,*args,**options):
            super().__init__(*args,**options)
            from rainier_data import installed
            self.needs_grid=installed() is None
            self.download_pool=None
            self.download_job=None
            self.download_message='USGS elevation is required for this walk.'

        def lines(self):
            if self.needs_grid:
                return ('Rainier walk',self.download_message,'[ Download Rainier terrain ]' if not self.download_job else 'Downloading…')
            return super().lines()

        def poll_interval(self):
            if not self.needs_grid:return super().poll_interval()
            return .2 if self.download_job and self._active() else None

        def poll(self,force=False):
            if not self.needs_grid:return super().poll(force)
            if self.download_job and self.download_job.done():
                try:self.download_job.result();self.needs_grid=False
                except Exception as error:self.download_message=str(error)
                self.download_job=None

        def pointer(self,x,y,width,button=0,released=False):
            if button or released:return False
            if self.needs_grid:return self.key('d') if y==2 else False
            return self.key('left' if x<width//3 else 'right' if x>=2*width//3 else 'up')

        def close(self):
            if self.download_pool:self.download_pool.shutdown(wait=False,cancel_futures=True)
            super().close()

        def key(self,key,now=None):
            if key.lower()=='o' and self._sync():
                self.cancel_keys();self.host.activate('Scenery');return True
            if self.needs_grid and key in ('d','D','\r','\n'):
                if not self.download_job:
                    from concurrent.futures import ThreadPoolExecutor
                    from rainier_data import download
                    if not self.download_pool:self.download_pool=ThreadPoolExecutor(max_workers=1)
                    self.download_job=self.download_pool.submit(download)
                return True
            return super().key(key,now)
    form=RainierWalk(host,outdoors=True,name='Rainier walk',**options)
    form.help+=(('Terrain viewpoints',('O opens Scenery: original, wide, elevated and valley cameras.',
        'Scenery is a separate overview; returning here keeps your walking position.')),)
    return form


def outdoor_descriptor():
    """Optional app reference; Runtime owns canonical discovery/menu inclusion."""
    return dict(id='rainier-walk',title='Rainier walk',preferred_size=(90,32),minimum_size=(22,12),category='Experiments',
        description='Ground-level Rainier terrain, fictional ruins and existing wildlife meshes',
        help=(('Explore',('W/S walk; A/D strafe; arrows turn.','I/K look up/down; ground follows metre-scale terrain.','O opens saved terrain viewpoints in Scenery.',
                          'Fictional ruins; real elevation data; existing Lab marmot/eagle.')),),factory=create_outdoors)
