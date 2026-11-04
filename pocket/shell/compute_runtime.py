"""Startup-only selection of the bundled optional geometry kernels."""
import os
from pathlib import Path
import stat
import sys

# This app's reviewed binaries and adapters; no paths or guards from the environment.
ASSETS={
 'libn810compute.so':(70192,'716b3c303126ab5e2afcdfca2298a13e3c766d59ddd67fd3809e8a9ded8d1930'),
 'libn810normals.so':(70384,'6d57d0438d98944664f08481f0f31811a346b2d56d86f61ea933ca5c63ab49c7'),
 'libn810coverage.so':(70580,'ccf4ebc1a6ecd30123f0007cee91c3f1af40056a5f8b774bce9d9a894bd2c1fd'),
 'libn810finish.so':(70636,'613cedc94026f18b54e3dbb83e8fef42759aafe8083826336f8f7b1393d2fe00'),
 'libn810pixels.so':(71676,'748f5ec493ea273829082202a42dfa444d6d6f7c49312f07b0fc820b103dc033'),
 'n810pixels.py':(7263,'d7bb6c9ef2befbd8478a035908126682da2b53d9e29f038d3888c982925fb4fa'),
 'n810compute.py':(4028,'cc7bb2637eb3d06782ea66fc95dbe6f1a6475b831c376c69863fcb977e84e9b1'),
 'n810normals.py':(8713,'e2f012369f09512c8856d15bd3b4d9ed5fc2d4a2557e883509bc056927144a73'),
 'n810coverage.py':(5207,'b01b511efdab441943fcd380f00278b7778e0932a086be0ebdc11a00be3a9b09'),
 'n810finish.py':(3342,'341da7d18df7406364ec0524df154c7715dc53ed08753e551b788c71ed407ac0'),
}
_selection=dict(requested='auto',selected='not selected',reason='startup pending')

_pending = None


def defer(mode='auto'):
    """Select geometry only when a geometry consumer first needs it."""
    global _pending
    _pending = mode
    if "geometry_compute" in sys.modules:ensure_selected()


def ensure_selected():
    global _pending
    if _pending is not None:
        mode, _pending = _pending, None
        select(mode)


def _verify(directory):
    import hashlib
    for name,(size,wanted) in ASSETS.items():
        fd=os.open(directory/name,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size!=size:raise ValueError('invalid bundled asset: '+name)
            with os.fdopen(fd,'rb',closefd=False) as stream:data=stream.read(size+1)
            if len(data)!=size or hashlib.sha256(data).hexdigest()!=wanted:raise ValueError('bundled asset hash mismatch: '+name)
        finally:os.close(fd)

def _portable(compute):
    compute.configure(None);compute.configure_normals(None)
    compute.configure_coverage(None);compute.configure_finish(None);compute.configure_pixels(None)

def select(mode='auto',directory=None):
    """Call before any scene worker/cache; failure resets the complete pipeline."""
    import geometry_compute as compute
    global _selection
    if mode not in ('auto','python','existing'):raise ValueError('invalid compute selection')
    if mode=='existing':
        _selection=dict(requested=mode,selected='caller configured',reason=None)
        return status()
    _portable(compute)
    _selection=dict(requested=mode,selected='python',reason='explicit Python selection')
    if mode=='python':return status()
    if sys.platform=='darwin':
        try:
            import host_geometry_runtime
            host_geometry_runtime.select()
        except (OSError,ValueError,RuntimeError,ImportError,AttributeError,SyntaxError,TypeError) as error:
            _portable(compute)
            _selection=dict(requested=mode,selected='python',reason='host stages: '+type(error).__name__+': '+str(error))
        else:_selection=dict(requested=mode,selected='native-c',reason=None)
        return status()
    if sys.platform!='linux' or os.uname().machine!='armv6l':
        _selection['reason']='bundled native kernels target Linux ARMv6'
        return status()
    if not compute._reference_sum_supported():
        _selection['reason']='reference sum guard requires ordinary summation'
        return status()
    directory=Path(directory) if directory is not None else Path(__file__).resolve().parent/'vendor/native'
    stage='assets'
    try:
        _verify(directory)
        stage='projection'
        if compute.configure(directory/'libn810compute.so',directory/'n810compute.py')['backend']!='native-vfp':raise ValueError('native VFP/FP environment unavailable')
        for stage,method,key in (('normals',compute.configure_normals,'normal_backend'),('coverage',compute.configure_coverage,'coverage_backend'),('finish',compute.configure_finish,'finish_backend'),('pixels',compute.configure_pixels,'pixel_backend')):
            selected=method(directory/('libn810'+stage+'.so'))
            if selected[key]!='native-vfp':raise ValueError('native VFP/FP environment unavailable')
    except (OSError,ValueError,RuntimeError,ImportError,AttributeError,SyntaxError,TypeError) as error:
        _portable(compute)
        _selection=dict(requested=mode,selected='python',reason=stage+': '+type(error).__name__+': '+str(error))
    else:_selection=dict(requested=mode,selected='native-vfp',reason=None)
    return status()

def status():
    import geometry_compute
    return dict(selection=dict(_selection),actual=geometry_compute.status())

def summary():
    data=status();actual=data['actual']
    fallback=any(actual.get(k,0) for k in ('reference_fallback_points','depth_fallback_batches','normal_fallbacks','coverage_fallbacks','finish_fallbacks','pixel_fallbacks','pixel_pack_fallbacks'))
    used=any(actual.get(k,0) for k in ('native_points','depth_native_points','normal_triangles','coverage_steps','finish_batches','pixel_batches'))
    if fallback:return 'fallback recorded (see Compute)'
    if used:return 'native calls recorded'
    return 'native VFP ready' if data['selection']['selected']=='native-vfp' else 'native C ready' if data['selection']['selected']=='native-c' else 'Python / portable'

def rows():
    def get(key):return status()['actual'].get(key,0)
    return [('Compute selection',lambda:status()['selection']['selected'],lambda d:None),
            ('Compute reason',lambda:status()['selection']['reason'] or 'ABI / hardware / FP guards passed',lambda d:None),
            ('Projection calls',lambda:f"N {get('native_points')} / P {get('python_points')} / F {get('reference_fallback_points')}",lambda d:None),
            ('Clipping depths',lambda:f"N {get('depth_native_points')} / fallback {get('depth_fallback_batches')}",lambda d:None),
            ('Normal triangles',lambda:f"N {get('normal_triangles')} / fallback {get('normal_fallbacks')}",lambda d:None),
            ('Coverage steps',lambda:f"N {get('coverage_steps')} / fallback {get('coverage_fallbacks')}",lambda d:None),
            ('Pixel samples',lambda:f"N {get('pixel_samples')} / fallback {get('pixel_fallbacks')} / water {get('pixel_water_samples')} / packed {get('pixel_packed_samples')}",lambda d:None),
            ('Material batches',lambda:f"N {get('finish_batches')} / fallback {get('finish_fallbacks')}",lambda d:None)]
