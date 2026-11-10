"""Host libraries/core build; no device operations or proprietary inputs."""
from pathlib import Path
import os,subprocess,json,importlib.util
r=Path(os.environ['SYMBIAN_HOST_BUILD_ROOT']);os.environ['TMPDIR']=str(r/'tmp')
os.environ['PKG_CONFIG_SYSROOT_DIR']=str(r/'deps');os.environ['PKG_CONFIG_LIBDIR']=str(r/'deps/usr/lib/aarch64-linux-gnu/pkgconfig')
os.environ['CMAKE_BUILD_PARALLEL_LEVEL']='4'
p=r/'src/emu/drivers/src/graphics/backend/ogl/graphics_ogl.cpp';s=p.read_text().replace('std::strcmp(fixed, "gpu")','std::strcmp(fixed, "cpu")');p.write_text(s)
p=r/'src/emu/kernel/src/scheduler.cpp';s=p.read_text()
s=s.replace('#ifdef EKA2L1_N810_PRIVATE_OSMESA\n#include "direct_core.h"','#if defined(EKA2L1_N810_PRIVATE_OSMESA) && !defined(SYMBIAN_HOST_CPU_BASELINE)\n#include "direct_core.h"')
s=s.replace('#ifdef EKA2L1_N810_PRIVATE_OSMESA\n                if (auto *native','#if defined(EKA2L1_N810_PRIVATE_OSMESA) && !defined(SYMBIAN_HOST_CPU_BASELINE)\n                if (auto *native')
if p.read_text()!=s:p.write_text(s)
(r/'src/external/uvw/uvw.hpp').write_text('#pragma once\n#include "src/uvw.hpp"\n')
libraries=[('yaml-cpp',['-DYAML_CPP_BUILD_TESTS=OFF','-DYAML_CPP_BUILD_TOOLS=OFF','-DYAML_CPP_BUILD_CONTRIB=OFF']),('re2',['-DRE2_BUILD_TESTING=OFF']),('libuv',['-DLIBUV_BUILD_SHARED=OFF','-DLIBUV_BUILD_TESTS=OFF','-DLIBUV_BUILD_BENCH=OFF']),('lunasvg',['-DLUNASVG_BUILD_EXAMPLES=OFF','-DPLUTOVG_BUILD_EXAMPLES=OFF','-DLUNASVG_DISABLE_LOAD_SYSTEM_FONTS=ON']),('mbedtls',['-DENABLE_TESTING=OFF','-DENABLE_PROGRAMS=OFF','-DUSE_SHARED_MBEDTLS_LIBRARY=OFF']),('libfat',[]),('pugixml',['-DPUGIXML_BUILD_TESTS=OFF']),('capstone',['-DCAPSTONE_ARCHITECTURE_DEFAULT=OFF','-DCAPSTONE_ARM_SUPPORT=ON','-DCAPSTONE_BUILD_TESTS=OFF','-DCAPSTONE_BUILD_CSTOOL=OFF']),('miniupnp/miniupnpc',['-DUPNPC_BUILD_STATIC=ON','-DUPNPC_BUILD_SHARED=OFF','-DUPNPC_BUILD_TESTS=OFF','-DUPNPC_BUILD_SAMPLE=OFF']),('cubeb',['-DBUILD_TESTS=OFF','-DBUILD_TOOLS=OFF','-DUSE_SANITIZERS=OFF','-DBUNDLE_SPEEX=ON','-DUSE_ALSA=OFF','-DUSE_PULSE=OFF','-DUSE_JACK=OFF','-DUSE_SNDIO=OFF','-DUSE_AAUDIO=OFF'])]
for name,opts in libraries:
 b=r/'libraries'/name;b.mkdir(parents=True,exist_ok=True)
 with (b/'build.log').open('w') as log:
  subprocess.run(['cmake','-S',str(r/'src/external'/name),'-B',str(b),'-DCMAKE_BUILD_TYPE=Release','-DBUILD_SHARED_LIBS=OFF','-DCMAKE_C_FLAGS=-O2 -ffunction-sections -fdata-sections','-DCMAKE_CXX_FLAGS=-O2 -ffunction-sections -fdata-sections','-DCMAKE_PREFIX_PATH='+str(r/'deps/usr'),*opts],stdout=log,stderr=subprocess.STDOUT,check=True)
  subprocess.run(['cmake','--build',str(b),'-j4']+(['--target','uv_a'] if name=='libuv' else []),stdout=log,stderr=subprocess.STDOUT,check=True)
 print('LIBRARY_OK',name,flush=True)
subprocess.run(['python3',str(r/'build_core.py')],env=dict(os.environ,N810_BUILD_JOBS='2'),check=True)
spec=importlib.util.spec_from_file_location('core',r/'build_core.py');core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
core.flags += ['-I'+str(r/'src/external/libtess2/Source')]
cpp=[r/'src/external/uvlooper/src/uvlooper.cpp']+list((r/'src/external/RectangleBinPack').glob('*.cpp'))
cpp=[p for p in cpp if p.name not in ['MaxRectsBinPackTest.cpp','boost_binpacker.cpp']]
extra=[core.compile(p) for p in cpp]
for p in [r/'src/runtime-port/native_memory.c',r/'src/external/glad/src/glad.c',r/'src/external/xxHash/xxhash.c']+list((r/'src/external/libtess2/Source').glob('*.c')):
 o=core.out/(str(p.relative_to(r/'src')).replace('/','_')+'.o')
 subprocess.run(['gcc','-O2','-ffunction-sections','-fdata-sections',*['-I'+str(x) for x in core.incs],'-c',str(p),'-o',str(o)],check=True)
 extra.append({'source':str(p.relative_to(r/'src')),'ok':True})
assert all(x['ok'] for x in extra)
records=json.loads((r/'compile-results.json').read_text())+extra
objects=[]
for item in records:
 p=Path(item['source']);name=str(p.relative_to(r/'src')) if p.is_absolute() else str(p);objects.append(core.out/(name.replace('/','_')+'.o'))
archives=list((r/'libraries').rglob('*.a'));libs=r/'deps/usr/lib/aarch64-linux-gnu'
args=['g++','-Wl,--gc-sections','-Wl,--start-group',*map(str,objects),*map(str,archives),'-Wl,--end-group','-L'+str(libs),'-Wl,-rpath,'+str(libs),'-Wl,-rpath-link,'+str(libs),'-lOSMesa','-lfreetype','-lsqlite3','-larchive','-lz','-pthread','-ldl','-o',str(r/'symbian-host-runtime')]
(r/'link-command.json').write_text(json.dumps(args,indent=2))
with (r/'link.log').open('w') as log:subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True)
print('HOST_RUNTIME_LINKED',flush=True)
