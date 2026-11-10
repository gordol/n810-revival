# SPDX-License-Identifier: GPL-2.0-or-later
"""Local native-pixel GUI regression: forbid full desktop cell composition."""
from pathlib import Path
import importlib.util,json,os,sys,tempfile
HERE=Path(__file__).resolve().parent

def main():
    sys.path[:0]=[str(HERE),str(HERE.parent/'shell')]
    import core
    original=core.Host.flush;old=os.environ.get('POCKET_NATIVE_PIXELS');old_data=os.environ.get('POCKET_DATA_ROOT');argv=sys.argv
    def forbidden(*args,**kwargs):raise AssertionError('Pixel GUI called Host.flush')
    try:
        with tempfile.TemporaryDirectory(prefix='pocket-pixel-check-') as directory:
            folder=Path(directory);os.environ['POCKET_NATIVE_PIXELS']='1';os.environ['POCKET_DATA_ROOT']=str(folder/'data')
            core.Host.flush=forbidden
            actions=folder/'actions.json';report=folder/'report.json'
            actions.write_text(json.dumps([{'menu':True},{'key':'\u001b'},{'launch':'window:Messages'},{'launch':'window:Settings'},{'launch':'terminal:new'},{'app':'surface-room'},{'resize':[110,34]},{'resize':[100,30]}]))
            spec=importlib.util.spec_from_file_location('native_pixel_run',HERE/'run.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            sys.argv=['run.py','--headless','--seconds','2','--state',str(folder/'state'),'--actions',str(actions),'--report',str(report),'--effect-backend','cpu','--effect','flux','--no-save','--no-local-services','--no-animation','--allow-software']
            module.main();data=json.loads(report.read_text());scene=data['gpu_scene']
            assert scene['native_pixel_frames']>5 and scene['desktop_cell_compositions']==0
            assert scene['flux_geometry_builds']>1, 'Native Flux model did not advance'
            assert data['menu_opened'] and not data['errors'] and data['desktop_cells']==[100,30]
            assert data['pixel_apps']['Surface room']['frames']>0
            assert not data['pixel_apps']['Surface room']['cell_layer']
            static_report=folder/'static.json'
            sys.argv=['run.py','--headless','--seconds','2','--state',str(folder/'static-state'),'--report',str(static_report),'--effect-backend','cpu','--no-save','--no-local-services','--no-animation','--allow-software']
            module.main();idle=json.loads(static_report.read_text())
            assert 0<idle['frames']<12, 'Static desktop redrew continuously'
            print(json.dumps(dict(result='passed',scope='local only',frames=data['frames'],static_frames=idle['frames'],full_desktop_cell_compositions=0,menu=True,room=True,resize=True)))
    finally:
        core.Host.flush=original;sys.argv=argv
        for key,value in [('POCKET_NATIVE_PIXELS',old),('POCKET_DATA_ROOT',old_data)]:
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
if __name__=='__main__':main()
