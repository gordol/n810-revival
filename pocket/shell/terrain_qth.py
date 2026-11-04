"""One explicit saved QTH, independent of temporary path endpoints and windows."""
from pathlib import Path
from runtime_codec import atomic_write,unpack
from terrain_elevation import coordinate

class QTH:
    def __init__(self,path):self.path=Path(path)
    def read(self):
        if not self.path.is_file():return None
        with self.path.open('rb') as source:value=unpack(source.read(4097),limit=4096)
        if not isinstance(value,dict) or value.get('version')!=1:raise ValueError('Invalid QTH settings')
        lat,lon=coordinate(f"{value['latitude']},{value['longitude']}")
        height=float(value.get('height_m',2))
        if not 0<=height<=10000:raise ValueError('Invalid QTH antenna height')
        return dict(value,latitude=lat,longitude=lon,height_m=height)
    def save(self,latitude,longitude,height_m=2,source='Selected by user'):
        latitude,longitude=coordinate(f'{latitude},{longitude}')
        if not 0<=height_m<=10000:raise ValueError('Invalid QTH antenna height')
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        atomic_write(self.path,dict(version=1,latitude=latitude,longitude=longitude,height_m=height_m,source=source))
