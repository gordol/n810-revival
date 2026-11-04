#!/usr/bin/env python3
"""Build the pinned native Reticulum service library outside the source tree."""
import argparse
import pathlib
import subprocess
HERE=pathlib.Path(__file__).resolve().parent
URLS=dict(microlxmf='attermann/microLXMF',microreticulum='attermann/microReticulum',arduinojson='bblanchon/ArduinoJson',
          msgpack='hideakitai/MsgPack',arxcontainer='hideakitai/ArxContainer',
          arxtypetraits='hideakitai/ArxTypeTraits',debuglog='hideakitai/DebugLog',
          crypto='attermann/Crypto',microstore='attermann/microStore')
p=argparse.ArgumentParser();p.add_argument('directory',type=pathlib.Path);p.add_argument('--arm',action='store_true');p.add_argument('--cmake',default='cmake');p.add_argument('--bzip2-library');p.add_argument('--install',action='store_true',help='Install the built library into this checkout for make n810');args=p.parse_args()
root=args.directory.resolve();root.mkdir(parents=True,exist_ok=True)
inputs={}
for line in (HERE/'dependencies.lock').read_text().splitlines():
    name,sha=line.split();path=root/name
    if not path.exists():subprocess.run(['git','clone','https://github.com/'+URLS[name]+'.git',str(path)],check=True)
    subprocess.run(['git','-C',str(path),'checkout','--detach',sha],check=True)
    if subprocess.check_output(['git','-C',str(path),'status','--porcelain'],text=True).strip():raise RuntimeError('Modified dependency: '+name)
    inputs[name]=path
options=['-DLXMF_SOURCE='+str(inputs.pop('microlxmf')),'-DRNS_SOURCE='+str(inputs.pop('microreticulum')),'-DCMAKE_BUILD_TYPE=Release']
options += ['-DRNS_'+name.upper()+'_SOURCE_DIR='+str(path) for name,path in inputs.items()]
if args.arm:
    options += ['-DCMAKE_SYSTEM_NAME=Linux','-DCMAKE_SYSTEM_PROCESSOR=arm',
                '-DCMAKE_C_COMPILER=arm-linux-gnueabi-gcc','-DCMAKE_CXX_COMPILER=arm-linux-gnueabi-g++',
                '-DCMAKE_C_FLAGS=-march=armv6 -mfpu=vfp -mfloat-abi=soft',
                '-DCMAKE_CXX_FLAGS=-march=armv6 -mfpu=vfp -mfloat-abi=soft']
if args.bzip2_library:options += ['-DBZIP2_LIBRARY_RELEASE='+args.bzip2_library]
subprocess.run([args.cmake,'-S',str(HERE),'-B',str(root/'build')]+options,check=True)
subprocess.run([args.cmake,'--build',str(root/'build'),'-j4'],check=True)

import hashlib,json,platform
build=root/'build'
library=build/('libpocket_rns.so' if args.arm or platform.system()=='Linux' else 'libpocket_rns.dylib')
manifest=dict(version=1,abi=2,platform='Linux-armv6l' if args.arm else platform.system()+'-'+platform.machine(),library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),sources={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in ('engine.cpp','prepare.py','CMakeLists.txt','dependencies.lock')},options=options)
(build/'provenance.json').write_text(json.dumps(manifest,indent=2)+'\n')

if args.install:
    import shutil
    target=HERE.parents[1]/'vendor/native'
    target.mkdir(parents=True,exist_ok=True)
    shutil.copy2(library,target/library.name)
    shutil.copy2(build/'provenance.json',target/'libpocket_rns.provenance.json')
