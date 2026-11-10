"""Run in the local Linux VM. Isolated host CPU variant; no device operations."""
from pathlib import Path
import shutil,subprocess,os,json
r=Path(os.environ['SYMBIAN_HOST_BUILD_ROOT']);original=Path(os.environ['SYMBIAN_NATIVE_BUILD_ROOT'])
os.environ['TMPDIR']=str(r/'tmp')
for package in (r/'packages').glob('*.deb'):subprocess.run(['dpkg-deb','-x',str(package),str(r/'deps')],check=True)
if not (r/'src').exists():shutil.copytree(original/'src',r/'src',ignore=shutil.ignore_patterns('.git','__pycache__'))
s=r/'src';port=s/'runtime-port'
def edit(path,old,new):
 text=path.read_text();assert old in text,(path,old[:80]);path.write_text(text.replace(old,new))
# Explicit host interpreter, never a silent fallback in the device binary.
p=port/'runtime_main.cpp';text=p.read_text();start=text.index('    const char *cpu_backend=');end=text.index('    n810_fault::install();',start)
text=text[:start]+'''    const char *cpu_backend=std::getenv("N810_SYMBIAN_CPU");
    if(!cpu_backend||std::strcmp(cpu_backend,"dyncom"))throw std::runtime_error("Host baseline requires explicit dyncom interpreter");
'''+text[end:]
text=text.replace('#include "native_fast_exec.h"','').replace('    apply_native_fast_exec(runtime.get_memory_system(),runtime.get_cpu());','')
text=text.replace('conf.cpu_backend = "12l1r"','conf.cpu_backend = "dyncom"').replace('arm_emulator_type::r12l1','arm_emulator_type::dyncom').replace('cpu_backend=native direct_arm=1 interpreter=0 jit=0','cpu_backend=dyncom direct_arm=0 interpreter=1 jit=0 host_baseline=1')
p.write_text(text)
p=s/'emu/cpu/src/arm_factory.cpp';edit(p,'#ifdef EKA2L1_N810_PRIVATE_OSMESA','#if defined(EKA2L1_N810_PRIVATE_OSMESA) && !defined(SYMBIAN_HOST_CPU_BASELINE)')
p=s/'emu/kernel/src/scheduler.cpp';text=p.read_text()
text=text.replace('#ifdef EKA2L1_N810_PRIVATE_OSMESA\n#include "direct_core.h"','#if defined(EKA2L1_N810_PRIVATE_OSMESA) && !defined(SYMBIAN_HOST_CPU_BASELINE)\n#include "direct_core.h"')
text=text.replace('#ifdef EKA2L1_N810_PRIVATE_OSMESA\n                if (auto *native', '#if defined(EKA2L1_N810_PRIVATE_OSMESA) && !defined(SYMBIAN_HOST_CPU_BASELINE)\n                if (auto *native')
p.write_text(text)
# Host-only diagnostics use native AArch64 ucontext, not ARM32 register fields.
for name in ('fault_capture.h','native_cpu_profile.h','host_graphics_profile.h'):
 p=port/name;text=p.read_text()
 for a,b in [('arm_pc','pc'),('arm_lr','regs[30]'),('arm_cpsr','pstate'),('arm_sp','sp'),('arm_ip','regs[12]')]+[(f'arm_r{i}',f'regs[{i}]') for i in range(15,-1,-1)]:text=text.replace('.'+a,'.'+b)
 p.write_text(text)
# Same compatibility GL sprite pipeline, explicitly software-rendered on host.
p=port/'context_osmesa.cpp';text=p.read_text().replace('std::strcmp(requested, "gpu")','std::strcmp(requested, "cpu")').replace('Symbian graphics requires MBX GPU mode; software rendering is disabled','Host baseline requires explicit CPU renderer')
text=text.replace('std::strcmp(renderer,"Nokia MBX GPU transform, lighting and rasterizer")','std::strcmp(renderer,"softpipe")').replace('GPU mode requires the verified MBX renderer; no software fallback','Host baseline requires verified softpipe CPU renderer')
text=text.replace('Nokia MBX GPU transform, lighting and rasterizer (verified graphics thread)','softpipe CPU renderer (verified graphics thread)').replace('graphics_fixed_function=gpu','graphics_fixed_function=cpu')
p.write_text(text)
p=s/'emu/drivers/src/graphics/backend/ogl/graphics_ogl.cpp';edit(p,'std::strcmp(fixed,"gpu")','std::strcmp(fixed,"cpu")')
# The mask operation is exactly RGB from source plus alpha from mask red.
# Keep all existing layout/sampler/size checks. No MBX device is opened on host.
p=port/'gpu_mask_texture.h';text=p.read_text();a=text.index(' const char *fdstr=');b=text.index(' glFinish();',a);text=text[:a]+text[b:]
a=text.index(' // Each independent pointwise');b=text.index(' GLuint texture=0;',a)
text=text[:a]+''' // Host baseline only: explicit CPU channel selection, same pointwise result.
 for(size_t i=0;i<inputs[0].size();i+=4)inputs[0][i+3]=inputs[1][i+2];
'''+text[b:];p.write_text(text)
# Mapped output for timing and private captures, no window/display takeover.
(port/'host_frame_sink.h').write_text('''#pragma once
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <cstring>
#include <stdexcept>
inline void host_frame_sink(const unsigned char *pixels,unsigned w,unsigned h){
 static unsigned char *mapping=[](){int fd=open("host-frame.rgba",O_RDWR|O_CREAT|O_TRUNC|O_CLOEXEC,0600);if(fd<0||ftruncate(fd,16+800*480*4))throw std::runtime_error("host frame open");void *p=mmap(nullptr,16+800*480*4,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);close(fd);if(p==MAP_FAILED)throw std::runtime_error("host frame map");return (unsigned char*)p;}();
 if(!w||!h||w>800||h>480)throw std::runtime_error("host frame dimensions");
 auto *header=(unsigned*)mapping;__atomic_add_fetch(header,1,__ATOMIC_SEQ_CST);header[1]=w;header[2]=h;std::memcpy(mapping+16,pixels,size_t(w)*h*4);__atomic_add_fetch(header,1,__ATOMIC_SEQ_CST);
}
''')
p=port/'graphics_session.h';edit(p,'#include "present_fb.h"','#include "present_fb.h"\n#include "host_frame_sink.h"');edit(p,'            auto number=++frames;','            host_frame_sink(rgba,w,h);\n            auto number=++frames;')
# Reuse the exact source inventory, replace only host compiler/ABI selection.
text=(original/'build_core.py').read_text();a=text.index("r=Path(");b=text.index("modules=",a)
text=text[:a]+'''r=Path(os.environ['SYMBIAN_HOST_BUILD_ROOT']);s=r/'src';out=r/'objects';out.mkdir(exist_ok=True)
os.environ['TMPDIR']=str(r/'tmp')
def write_changed(p,text):
 if not p.exists() or p.read_text()!=text:p.write_text(text)
gen=r/'generated/common';gen.mkdir(parents=True,exist_ok=True)
write_changed(gen/'version.h','#pragma once\\n#define GIT_BRANCH "host-baseline"\\n#define GIT_COMMIT_HASH "d27ee467"\\n')
write_changed(gen/'configure.h','#pragma once\\n#define CURRENT_EKA2L1_VERSION_STRING "0.0.9-host-baseline"\\n')
compiler='g++'
flags=['-std=c++20','-O2','-g1','-DSPDLOG_FMT_EXTERNAL','-DFMT_HEADER_ONLY','-ffunction-sections','-fdata-sections','-Wno-invalid offsetof','-DEKA2L1_N810_PRIVATE_OSMESA','-DSYMBIAN_HOST_CPU_BASELINE','-DEKA2L1_CPU_DYNCOM_ONLY_BUILD=1']
flags.remove('-Wno-invalid offsetof');flags.append('-Wno-invalid offsetof'.replace(' ', '-'))
incs=[s/'runtime-port',s/'external',r/'deps/usr/include',r/'deps/usr/include/aarch64-linux-gnu',r/'deps/usr/include/freetype2']+list((s/'emu').glob('*/include'))+[r/'generated']
incs += [s/'external'/p for p in ['fmt/include','spdlog/include','yaml-cpp/include','glm','xxHash','re2','uvw','libuv/include','pugixml/src','capstone/include','stb','RectangleBinPack','libtess2/Include','microprofile','libfat','thread-pool/include','lunasvg/include','mbedtls/include','miniupnp/miniupnpc/include','uvlooper/include','libfat/include','glad/include','cubeb/include']]
flags += ['-I'+str(p) for p in incs]
''' +text[b:]
text=text.replace("sources += list((s/'emu/cpu/src/12l1r').glob('*.cpp')) + list((s/'emu/cpu/src/12l1r/translate').glob('*.cpp'))","sources += [s/'emu/cpu/src/12l1r/exclusive_monitor.cpp']")
text=text.replace("'frontend_ui.cpp','direct_core.cpp','fixed_sprite.cpp'","'frontend_ui.cpp','fixed_sprite.cpp'").replace("r/'cubeb-build/exports'","r/'libraries/cubeb/exports'")
(r/'build_core.py').write_text(text)
(r/'prepared.json').write_text(json.dumps({'host_arch':os.uname().machine,'cpu':'dyncom interpreter','renderer':'softpipe CPU','device_build_modified':False},indent=2))
print('Host-only overlays prepared',flush=True)
