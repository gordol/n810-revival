"""Package committed Pocket source for the existing guarded Nokia supervisor."""
import argparse
import ast
import gzip
import hashlib
import io
import json
import re
from pathlib import Path
import subprocess
import tarfile
from nokia_release_verify import verify, PLATFORM_FILES, HOST_GEOMETRY

ROOT=Path(__file__).resolve().parents[1]
BASELINE='5e63c3ffdef4b8ece894f85efe2a6ba46062fd39acf4ed129dabcdeafdded319'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def selector_pin(value):
    if not re.fullmatch(r'[0-9a-f]{64}',value):raise argparse.ArgumentTypeError('Selector pin must be a lowercase SHA256 digest')
    return value
def encoded(value):return (json.dumps(value,indent=2)+'\n').encode()
def compositor_files(directory,source):
    """Accept a rebuilt target only with matching source and ARM ABI provenance."""
    library=(directory/'_cellengine.abi3.so').read_bytes()
    provenance=(directory/'provenance.json').read_bytes();record=json.loads(provenance)
    identity=record.get('identity',{})
    expected={name:sha(source['native/'+name]) for name in ('cell_module.c','cell_engine.c','window_host.c','scene_host.c','blend_host.c','input_pump.c')}
    if identity.get('system')!='Linux' or identity.get('machine')!='armv6l' or identity.get('python_tag')!='cpython-311' or identity.get('abi')!='CPython limited API 3.11' or identity.get('sources')!=expected or record.get('sha256')!=sha(library):
        raise ValueError('Native compositor build identity mismatch')
    if len(library)<52 or library[:6]!=b'\x7fELF\x01\x01' or int.from_bytes(library[18:20],'little')!=40:
        raise ValueError('Native compositor must be 32-bit little-endian ARM ELF')
    flags=int.from_bytes(library[36:40],'little')
    if flags&0xff000000!=0x05000000 or not flags&0x200 or flags&0x400:
        raise ValueError('Native compositor requires ARM EABI5 soft float')
    return {prefix+name:raw for prefix in ('vendor/native/','native/build-host/Linux-armv6l-cpython-311/')
            for name,raw in (('_cellengine.abi3.so',library),('_cellengine.provenance.json' if prefix=='vendor/native/' else 'provenance.json',provenance))}

def require_native_reticulum(files):
    """A Nokia release must never depend on an uninstalled Python fallback."""
    try:
        library=files['vendor/native/libpocket_rns.so']
        record=json.loads(files['vendor/native/libpocket_rns.provenance.json'])
    except KeyError as error:
        raise ValueError('Nokia releases require microReticulum; supply --native-reticulum with a tested ARM build') from error
    if record.get('abi')!=2 or record.get('platform')!='Linux-armv6l' or record.get('library_sha256')!=sha(library):
        raise ValueError('Native Reticulum build identity mismatch')
def runtime_files(files):
    """Repository tests stay in Git; they are not installed application code."""
    map_root='vendor/map-library-resources/explorations/current-world/'
    map_worker={'paint.py','offline_map.py','map_tiles.py','map_palette.py',
                'experiments/map-drag-trial/geographic_palette.py',
                'experiments/map-drag-trial/regional-pack-v2/bake.py'}
    duplicates=('vendor/apps/experiments/cw-reference/', 'vendor/packet-console/experiments/cw-reference/')
    build_trees=('apps/doom-app/vendor/doomgeneric/','native/reticulum/')
    notices={'LICENSE','LICENSE.txt','COPYING','NOTICE','NOTICE.md','UPSTREAM.md','SOURCE.json','MsgPack-LICENSE'}
    result={}
    for name,raw in files.items():
        if name=='vendor/apps/domains/reticulum/desktop_stack.py':continue
        leaf=Path(name).name
        if name.startswith(build_trees) and leaf not in notices:continue
        if 'tests' in Path(name).parts or '__pycache__' in Path(name).parts or leaf.startswith(('test-', 'test_', 'bench-', 'benchmark')) or leaf=='bench.py':continue
        if name.startswith('vendor/packet-console/fixtures/'):continue
        if name in ('apps/doom-app/build.py','apps/doom-app/bridge.c'):continue
        if name.startswith('native/accelerators/') and leaf in ('build.py','probe.c'):continue
        duplicate=next((prefix for prefix in duplicates if name.startswith(prefix)),None)
        if duplicate:
            if raw!=files.get('vendor/apps/cw-reference/'+name[len(duplicate):]):
                raise ValueError('CW copy diverged from its runtime source: '+name)
            continue
        if name.startswith(map_root) and name.endswith('.py') and name[len(map_root):] not in map_worker:continue
        result[name]=raw
    recipe='apps/map-library-local-v3/dependency-inventory.json'
    if recipe in result:
        inventory=json.loads(result[recipe])
        for row in inventory['files']:
            if 'vendor/map-library-resources/'+row['path'] not in files:
                raise ValueError('Pinned map input missing from source: '+row['path'])
        inventory['files']=[row for row in inventory['files'] if 'vendor/map-library-resources/'+row['path'] in result]
        result[recipe]=encoded(inventory)
    return result
def archive(files):
    output=io.BytesIO()
    with gzip.GzipFile(fileobj=output,mode='wb',filename='',mtime=0) as zipped:
        with tarfile.open(fileobj=zipped,mode='w') as tar:
            for name,raw in sorted(files.items()):
                entry=tarfile.TarInfo(name);entry.size=len(raw);entry.mode=0o644
                tar.addfile(entry,io.BytesIO(raw))
    return output.getvalue()
def adapt(raw,values):
    tree=ast.parse(raw);lines=raw.decode().splitlines(True);found=set()
    for node in reversed(tree.body):
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            if name in values:lines[node.lineno-1:node.end_lineno]=[name+'='+values[name]+'\n'];found.add(name)
    if found!=set(values):raise ValueError('Registrar constants changed')
    result=''.join(lines).encode()
    def normalized(source):
        tree=ast.parse(source)
        for node in tree.body:
            if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in values:node.value=ast.Constant(None)
        return ast.dump(tree,include_attributes=False)
    assert normalized(raw)==normalized(result)
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files',action='store_true',help='Stage runtime files for incremental compressed rsync instead of transferring an archive')
    parser.add_argument('--platform-release',type=Path,required=True,help='Verified original 5e63c3f Nokia archive')
    parser.add_argument('--selector-sha256',type=selector_pin,help='Reviewed installed selector digest after a separate capacity upgrade')
    parser.add_argument('--native-compositor',type=Path,help='Tested ARM compositor build directory with provenance.json')
    parser.add_argument('--native-reticulum',type=Path,help='Tested ARM native backend build directory with provenance.json')
    args=parser.parse_args()
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip():raise SystemExit('Commit the source first')
    product_version=(ROOT/'VERSION').read_text().strip()
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)',product_version):raise ValueError('VERSION must be MAJOR.MINOR.PATCH')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    baseline=verify(args.platform_release)
    if baseline['engine_sha256']!=BASELINE:raise ValueError('Unexpected platform baseline')
    source={name[6:]: (ROOT/name).read_bytes() for name in subprocess.check_output(['git','ls-files','shell'],cwd=ROOT,text=True).splitlines()}
    files=runtime_files(source)
    with tarfile.open(args.platform_release) as tar:
        # Reuse only reviewed original platform libraries; source equality is required.
        if args.native_compositor is None:
            for name in ('native/cell_module.c','native/cell_engine.c'):
                if files[name]!=tar.extractfile(name).read():raise ValueError('Rebuild native compositor for changed source')
        for name in baseline['platform_files']:
            if name!='build-info.json' and not name.startswith(HOST_GEOMETRY):files[name]=tar.extractfile(name).read()
    if args.native_compositor is not None:
        files.update(compositor_files(args.native_compositor,source))
    if args.native_reticulum is not None:
        library=(args.native_reticulum/'libpocket_rns.so').read_bytes()
        provenance=(args.native_reticulum/'provenance.json').read_bytes()
        record=json.loads(provenance)
        if record.get('abi')!=2 or record.get('platform')!='Linux-armv6l' or record.get('library_sha256')!=sha(library):raise ValueError('Native Reticulum build identity mismatch')
        for name,digest in record['sources'].items():
            if sha(source['native/reticulum/'+name])!=digest:raise ValueError('Rebuild native Reticulum for changed source: '+name)
        files['vendor/native/libpocket_rns.so']=library
        files['vendor/native/libpocket_rns.provenance.json']=provenance
    require_native_reticulum(files)
    identity=files['build_identity.py'].decode()
    marker='_PACKAGED_RELEASE=UNKNOWN'
    if identity.count(marker)!=1:raise ValueError('Packaged release identity marker changed')
    files['build_identity.py']=identity.replace(marker,'_PACKAGED_RELEASE='+repr(commit[:12])).encode()
    shared={name:sha(raw) for name,raw in files.items() if name not in PLATFORM_FILES}
    engine=sha(json.dumps(shared,sort_keys=True,separators=(',',':')).encode())
    files['build-info.json']=encoded(dict(schema_version=1,product_version=product_version,release_id=commit[:12],framework_commit=commit,domain_commit=commit,
        platform='n810',backend='native cells supplied',artifact_sha256=engine,touch_acquisition_default='process'))
    manifest=dict(version=2,engine_sha256=engine,source_commit=commit,shared_files=shared,
        platform_files=sorted(set(files)&PLATFORM_FILES),files={name:sha(raw) for name,raw in sorted(files.items())})
    files['device-poc/pocket-manifest.json']=encoded(manifest)
    raw=b'' if args.files else archive(files)
    if len(raw)>10*1024*1024:raise ValueError('Supervisor package limit exceeded')
    version='pocket-'+commit[:12];stage='/tmp/'+version+'-register'
    entry=dict(title='Pocket '+commit[:12],summary='Shell first; grouped device services, System telemetry and Reticulum.',
        engine_sha256=engine,manifest_sha256=sha(files['device-poc/pocket-manifest.json']),retained=version+'/candidate-assets')
    registration=(ROOT/'platform/n810/registration/register_candidate.py').read_bytes()
    selector_sha=next(ast.literal_eval(node.value) for node in ast.parse(registration).body
        if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='SELECTOR_SHA' for target in node.targets))
    values=dict(
        INPUT='Path('+repr(stage)+')',DESTINATION='Path('+repr('/var/backups/n810-pocket-console/'+version)+')',
        VERSION_ID=repr(version),PACKAGE_SHA=repr(sha(raw)),ENTRY=repr(entry),FILE_PAYLOAD=repr(args.files))
    if args.selector_sha256 is not None:
        selector_sha=args.selector_sha256
        values['SELECTOR_SHA']=repr(selector_sha)
    registrar=adapt(registration,values)
    output=ROOT/'dist'/(version+('-files' if args.files else ''));output.mkdir(parents=True,exist_ok=False)
    (output/'CONTENTS.json').write_bytes(encoded(dict(source_python=sum(n.endswith('.py') for n in source),
        runtime_python=sum(n.endswith('.py') for n in files),
        excluded=sorted(set(source)-set(files)),
        generated={name:dict(source_sha256=sha(source[name]),runtime_sha256=sha(raw))
                   for name,raw in files.items() if name in source and raw!=source[name]})))
    if args.files:
        for name,data in files.items():
            path=output/'files'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    else:
        (output/'nokia.tar.gz').write_bytes(raw);verify(output/'nokia.tar.gz')
    (output/'register_candidate.py').write_bytes(registrar)
    for name in ('session_entry.py','upgrade_session.py'):
        source=(ROOT/'platform/n810'/name).read_bytes()
        if name=='upgrade_session.py' and args.selector_sha256 is not None:
            source=adapt(source,dict(CURRENT_SELECTOR=repr(selector_sha)))
        (output/name).write_bytes(source)
    spp=(ROOT/'platform/n810/rnode_spp_prepare.py').read_bytes()
    (output/'rnode_spp_prepare.py').write_bytes(spp)
    predecessors=json.loads((ROOT/'platform/n810/rnode_spp_prepare.provenance.json').read_text())
    spp_predecessors=predecessors.get('predecessors',[predecessors['original_sha256']])
    installer=adapt((ROOT/'platform/n810/install.py').read_bytes(),dict(STAGE='Path('+repr(stage)+')',SPP_HELPER_SHA256=repr(sha(spp)),SPP_HELPER_PREDECESSORS=repr(tuple(spp_predecessors)),REGISTRAR_SHA256=repr(sha(registrar)),SESSION_ENTRY_SHA256=repr(sha((output/'session_entry.py').read_bytes())),SESSION_UPGRADE_SHA256=repr(sha((output/'upgrade_session.py').read_bytes())),ENGINE_SHA256=repr(engine),RECEIPT_DIRECTORY='Path('+repr('/var/backups/n810-pocket-console/'+version)+')'))
    (output/'install.py').write_bytes(installer)
    (output/'INSTALL.json').write_bytes(encoded(dict(version=version,product_version=product_version,commit=commit,engine=engine,stage=stage,
        files={'rnode_spp_prepare.py':sha(spp),**({} if args.files else {'nokia.tar.gz':sha(raw)}),'register_candidate.py':sha(registrar),'install.py':sha(installer),'session_entry.py':sha((output/'session_entry.py').read_bytes()),'upgrade_session.py':sha((output/'upgrade_session.py').read_bytes())},platform_baseline=BASELINE,
        transport='files' if args.files else 'archive',platform_archive_sha256=sha(args.platform_release.read_bytes()),selector_sha256=selector_sha,helper_unchanged=True,supervisor_unchanged=True,bluetooth_helper_sha256=sha(spp),radio_state_unchanged=True)))
    print(output)

if __name__=='__main__':main()
