"""Unprivileged installer/package fixtures; no installed paths or device access."""
import ast
from contextlib import ExitStack
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

installer=load('fixture_nokia_install',ROOT/'platform/n810/install.py')
sys.path.insert(0,str(ROOT/'tools'))
package=load('fixture_nokia_package',ROOT/'tools/package_nokia.py')
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def constants(path,names):
    result={}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in names:
            result[node.targets[0].id]=ast.literal_eval(node.value)
    return result


class InstallerFixtures(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='pocket-installer-');self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.stage=self.root/'package';self.stage.mkdir()
        self.destination=self.root/'root-stage';self.assets=self.root/'assets';self.assets.mkdir()
        self.receipt=self.root/'receipt';self.receipt.mkdir()
        self.raw={'register_candidate.py':b'# registrar fixture\n','session_entry.py':b'# entry fixture\n','upgrade_session.py':b'# upgrader fixture\n'}
        for name,raw in self.raw.items():(self.stage/name).write_bytes(raw)
        (self.assets/'device-poc').mkdir()
        (self.assets/'device-poc/pocket-manifest.json').write_text(json.dumps({'engine_sha256':'fixture-engine','files':{}}))
        self.events=[];self.owner_overrides={};self.mode_overrides={};self.fds={}
        self.real_open=os.open;self.real_fstat=os.fstat;self.real_lstat=Path.lstat
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        def local_path(value):
            return self.destination if str(value)=='/tmp/pocket-session-startup-upgrade' else Path(value)
        def opened(path,flags,*args,**kwargs):
            fd=self.real_open(path,flags,*args,**kwargs);self.fds[fd]=Path(path);return fd
        def info(path,original):
            uid=self.owner_overrides.get(path,0)
            mode=self.mode_overrides.get(path,original.st_mode)
            return SimpleNamespace(st_mode=mode,st_uid=uid,st_size=original.st_size)
        def fstat(fd):return info(self.fds.get(fd),self.real_fstat(fd))
        def lstat(path,*args,**kwargs):
            original=self.real_lstat(path,*args,**kwargs)
            return info(path,original) if path==self.destination else original
        def execute(code,namespace):
            name=Path(code.co_filename).name
            self.assertEqual(namespace['__name__'],'__main__')
            if name=='upgrade_session.py':
                self.assertEqual((self.destination/'session_entry.py').read_bytes(),self.raw['session_entry.py'])
            self.events.append(name)
        for target,value in (
            ('STAGE',self.stage),('ASSETS',self.assets),('RECEIPT_DIRECTORY',self.receipt),
            ('ENGINE_SHA256','fixture-engine'),('REGISTRAR_SHA256',sha(self.raw['register_candidate.py'])),
            ('SESSION_ENTRY_SHA256',sha(self.raw['session_entry.py'])),('SESSION_UPGRADE_SHA256',sha(self.raw['upgrade_session.py'])),
            ('Path',local_path),('exec',execute),
        ):self.stack.enter_context(patch.object(installer,target,value,create=True))
        self.stack.enter_context(patch.object(installer.os,'open',side_effect=opened))
        self.stack.enter_context(patch.object(installer.os,'fstat',side_effect=fstat))
        self.stack.enter_context(patch.object(Path,'lstat',autospec=True,side_effect=lstat))
        self.stack.enter_context(patch.object(installer.os,'geteuid',return_value=0))
        self.stack.enter_context(patch.object(installer.sys,'argv',['fixture-install']))

    def test_success_stages_verified_entry_then_upgrade_then_registrar(self):
        installer.main()
        self.assertEqual(self.events,['upgrade_session.py','register_candidate.py'])
        self.assertEqual((self.destination/'session_entry.py').read_bytes(),self.raw['session_entry.py'])
        receipt=json.loads((self.receipt/'BYTECODE.json').read_text())
        self.assertEqual(receipt['engine'],'fixture-engine');self.assertEqual(receipt['files'],{})

    def test_source_verified_at_install_and_cache_tracks_metadata(self):
        source=self.assets/'cached_fixture.py';source.write_text('value = 42\n')
        manifest=self.assets/'device-poc/pocket-manifest.json'
        manifest.write_text(json.dumps(dict(engine_sha256='fixture-engine',files={source.name:sha(source.read_bytes())})))
        installer.main()
        receipt=json.loads((self.receipt/'BYTECODE.json').read_text())
        self.assertEqual(receipt['invalidation'],'timestamp')
        cache=Path(importlib.util.cache_from_source(str(source)))
        self.assertEqual(int.from_bytes(cache.read_bytes()[4:8],'little'),0)
        self.assertEqual(receipt['files'][str(cache.relative_to(self.assets))]['source_sha256'],sha(source.read_bytes()))
        def imported():
            spec=importlib.util.spec_from_file_location('installed_cache_fixture',source)
            module=importlib.util.module_from_spec(spec)
            with patch.object(spec.loader,'get_data',wraps=spec.loader.get_data) as reads:
                spec.loader.exec_module(module)
            return module.value,[str(call.args[0]) for call in reads.call_args_list]
        value,reads=imported();self.assertEqual(value,42)
        self.assertNotIn(str(source),reads)
        previous=source.stat();source.write_text('value = 43\n')
        os.utime(source,(previous.st_atime,previous.st_mtime+2))
        value,reads=imported();self.assertEqual(value,43)
        self.assertIn(str(source),reads)

    def test_unchanged_module_reuses_bytecode_after_staging_changes_timestamp(self):
        source=self.assets/'reuse_fixture.py';source.write_text('value = 42\n')
        digest=sha(source.read_bytes())
        cache=Path(installer.py_compile.compile(str(source),doraise=True))
        old=cache.read_bytes();info=source.stat();os.utime(source,(info.st_atime,info.st_mtime+20))
        (self.assets/'build-info.json').write_text(json.dumps(dict(release_id='1234567890ab')))
        (self.assets/'device-poc/pocket-manifest.json').write_text(json.dumps(dict(engine_sha256='fixture-engine',files={source.name:digest})))
        with patch.object(installer,'previous_bytecode',return_value={(source.name,digest):old}),patch.object(installer.py_compile,'compile',side_effect=AssertionError('Unchanged source recompiled')):
            installer.main()
        self.assertEqual(cache.read_bytes()[16:],old[16:])
        self.assertEqual(int.from_bytes(cache.read_bytes()[8:12],'little'),int(source.stat().st_mtime))

    def test_changed_source_rejected_before_bytecode_preparation(self):
        source=self.assets/'changed_fixture.py';source.write_text('value = 42\n')
        manifest=self.assets/'device-poc/pocket-manifest.json'
        manifest.write_text(json.dumps(dict(engine_sha256='fixture-engine',files={source.name:sha(source.read_bytes())})))
        source.write_text('value = 43\n')
        with self.assertRaisesRegex(ValueError,'Source changed'):
            installer.main()
        self.assertFalse(Path(importlib.util.cache_from_source(str(source))).exists())

    def test_success_reuses_matching_root_owned_payload(self):
        self.destination.mkdir(mode=0o700)
        target=self.destination/'session_entry.py';target.write_bytes(self.raw['session_entry.py']);target.chmod(0o644)
        inode=target.stat().st_ino;installer.main()
        self.assertEqual(target.stat().st_ino,inode)
        self.assertEqual(self.events,['upgrade_session.py','register_candidate.py'])

    def test_corrupt_payloads_rejected_before_staging_or_execution(self):
        for name in self.raw:
            with self.subTest(payload=name):
                original=(self.stage/name).read_bytes();(self.stage/name).write_bytes(original+b'# changed\n')
                try:
                    with self.assertRaises(ValueError):installer.main()
                    self.assertFalse(self.destination.exists());self.assertEqual(self.events,[])
                finally:(self.stage/name).write_bytes(original)

    def test_session_payload_symlinks_nonregular_and_oversize_refused(self):
        for name in ('session_entry.py','upgrade_session.py'):
            for kind in ('symlink','directory','oversize'):
                with self.subTest(payload=name,kind=kind):
                    path=self.stage/name;path.unlink()
                    if kind=='symlink':path.symlink_to(self.stage/'register_candidate.py')
                    elif kind=='directory':path.mkdir()
                    else:path.write_bytes(b'x'*262145)
                    try:
                        with self.assertRaises((OSError,ValueError)):installer.main()
                        self.assertFalse(self.destination.exists());self.assertEqual(self.events,[])
                    finally:
                        if path.is_dir() and not path.is_symlink():path.rmdir()
                        else:path.unlink()
                        path.write_bytes(self.raw[name])

    def test_unsafe_root_stage_directory_refused(self):
        for kind in ('symlink','writable','nonroot'):
            with self.subTest(kind=kind):
                if kind=='symlink':self.destination.symlink_to(self.assets,target_is_directory=True)
                else:
                    self.destination.mkdir(mode=0o700)
                    if kind=='writable':self.destination.chmod(0o777)
                    else:self.owner_overrides[self.destination]=1000
                try:
                    with self.assertRaises(ValueError):installer.main()
                    self.assertEqual(self.events,[])
                finally:
                    self.owner_overrides.clear()
                    if self.destination.is_symlink():self.destination.unlink()
                    else:self.destination.rmdir()

    def test_unsafe_existing_staged_payload_refused(self):
        self.destination.mkdir(mode=0o700);target=self.destination/'session_entry.py'
        for kind in ('symlink','directory','fifo','different','writable','nonroot'):
            with self.subTest(kind=kind):
                if kind=='symlink':target.symlink_to(self.stage/'session_entry.py')
                elif kind=='directory':target.mkdir()
                elif kind=='fifo':os.mkfifo(target)
                else:
                    target.write_bytes(b'other' if kind=='different' else self.raw['session_entry.py'])
                    target.chmod(0o666 if kind=='writable' else 0o644)
                    if kind=='nonroot':self.owner_overrides[target]=1000
                try:
                    with self.assertRaises((ValueError,OSError)):installer.main()
                    self.assertEqual(self.events,[])
                finally:
                    self.owner_overrides.clear()
                    if target.is_dir() and not target.is_symlink():target.rmdir()
                    else:target.unlink()

    def test_failed_stopped_session_upgrade_prevents_registrar(self):
        def stop(code,namespace):
            self.events.append(Path(code.co_filename).name)
            raise RuntimeError('fixture console is not stopped/restored')
        with patch.object(installer,'exec',side_effect=stop):
            with self.assertRaisesRegex(RuntimeError,'not stopped'):installer.main()
        self.assertEqual(self.events,['upgrade_session.py'])
        self.assertFalse((self.receipt/'BYTECODE.json').exists())

    def test_privilege_and_arguments_refused_before_package_read(self):
        for uid,args in ((1000,['install']),(0,['install','extra'])):
            with self.subTest(uid=uid,args=args),patch.object(installer.os,'geteuid',return_value=uid),patch.object(installer.sys,'argv',args),patch.object(installer.os,'open',side_effect=AssertionError('opened before launch validation')):
                with self.assertRaises(SystemExit):installer.main()


class PackageContracts(unittest.TestCase):
    def test_rebuilt_compositor_requires_source_hash_and_target_abi(self):
        with tempfile.TemporaryDirectory(prefix='pocket-compositor-') as tmp:
            root=Path(tmp);source={'native/'+n:n.encode() for n in ('cell_module.c','cell_engine.c','window_host.c','scene_host.c','blend_host.c','input_pump.c')}
            library=bytearray(52);library[:6]=b'\x7fELF\x01\x01';library[18:20]=(40).to_bytes(2,'little');library[36:40]=(0x5000200).to_bytes(4,'little')
            path=root/'_cellengine.abi3.so';path.write_bytes(library)
            record=dict(identity=dict(system='Linux',machine='armv6l',python_tag='cpython-311',abi='CPython limited API 3.11',sources={n[7:]:sha(raw) for n,raw in source.items()}),sha256=sha(library))
            receipt=root/'provenance.json';receipt.write_text(json.dumps(record))
            self.assertEqual(len(package.compositor_files(root,source)),4)
            for mutation in ('source','library','hardfloat','architecture'):
                altered=dict(source);data=bytearray(library)
                if mutation=='source':altered['native/window_host.c']=b'changed'
                elif mutation=='library':data.append(1)
                elif mutation=='hardfloat':data[36:40]=(0x5000400).to_bytes(4,'little')
                else:data[18:20]=(183).to_bytes(2,'little')
                path.write_bytes(data)
                changed=json.loads(json.dumps(record))
                if mutation in ('hardfloat','architecture'):changed['sha256']=sha(data)
                receipt.write_text(json.dumps(changed))
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):package.compositor_files(root,altered)

    def test_runtime_package_excludes_development_files(self):
        files={'desktop.py':b'core', 'owner-service/test_feed.py':b'test',
               'vendor/domain/tests/probe.py':b'probe', 'vendor/maps/map.py':b'map',
               'vendor/maps/README.md':b'help', 'vendor/maps/bench-render.py':b'benchmark',
               'bench.py':b'bench','native/test_render.c':b'test',
               'native/__pycache__/unused.pyc':b'cache',
               'vendor/packet-console/fixtures/example.json':b'test fixture',
               'apps/doom-app/build.py':b'build','apps/doom-app/bridge.c':b'build',
               'apps/doom-app/vendor/doomgeneric/engine.c':b'build',
               'native/reticulum/engine.cpp':b'build',
               'native/accelerators/coverage/probe.c':b'probe',
               'native/accelerators/coverage/build.py':b'build'}
        self.assertEqual(set(package.runtime_files(files)),
                         {'desktop.py','vendor/maps/map.py','vendor/maps/README.md'})

    def test_runtime_retains_notices_feature_assets_and_verification_inputs(self):
        files={name:b'needed' for name in (
            'apps/doom-app/vendor/doomgeneric/LICENSE',
            'apps/doom-app/vendor/doomgeneric/SOURCE.json',
            'native/reticulum/vendor/microLXMF/LICENSE',
            'native/cell_module.c','native/accelerators/coverage/kernels.c',
            'vendor/apps/domains/reader/fixtures/field-notes.rss',
            'vendor/packet-console/tools/build-terrain-next.py','build_trace.py')}
        self.assertEqual(package.runtime_files(files),files)

    def test_duplicate_cw_sources_must_match_canonical_copy(self):
        canonical='vendor/apps/cw-reference/reference.py'
        copy='vendor/packet-console/experiments/cw-reference/reference.py'
        self.assertEqual(package.runtime_files({canonical:b'code',copy:b'code'}),{canonical:b'code'})
        with self.assertRaisesRegex(ValueError,'CW copy diverged'):
            package.runtime_files({canonical:b'code',copy:b'new code'})

    def test_map_recipe_pins_only_shipped_worker_inputs(self):
        base='vendor/map-library-resources/'
        paint='explorations/current-world/paint.py'
        scene='explorations/current-world/scenery.py'
        recipe='apps/map-library-local-v3/dependency-inventory.json'
        files={base+paint:b'paint',base+scene:b'scenery',recipe:json.dumps(dict(version=1,files=[dict(path=paint),dict(path=scene)])).encode()}
        result=package.runtime_files(files)
        self.assertIn(base+paint,result);self.assertNotIn(base+scene,result)
        self.assertEqual(json.loads(result[recipe])['files'],[dict(path=paint)])
        self.assertEqual(len(json.loads(files[recipe])['files']),2)

    def test_entry_selector_and_supervisor_hashes_close(self):
        values=constants(ROOT/'platform/n810/upgrade_session.py',{'NEW_ENTRY','OLD_ENTRY','NEW_SELECTOR','SUPERVISOR_SHA','HELPER_SHA'})
        registration=constants(ROOT/'platform/n810/registration/register_candidate.py',{'CONTRACTS'})['CONTRACTS']
        self.assertEqual(values['NEW_ENTRY'],sha((ROOT/'platform/n810/session_entry.py').read_bytes()))
        self.assertEqual(registration['/usr/local/libexec/n810-pocket-session'],values['NEW_ENTRY'])
        self.assertEqual(registration['/usr/local/lib/n810-pocket/console_helper.py'],values['SUPERVISOR_SHA'])
        self.assertEqual(registration['/usr/local/sbin/n810-pocket-console'],values['HELPER_SHA'])
        self.assertNotEqual(values['OLD_ENTRY'],values['NEW_ENTRY'])

    def test_fake_checkout_package_constants_and_file_hash_closure(self):
        self.check_package()

    def test_package_pins_reviewed_capacity_selector_and_receipt(self):
        self.check_package('b1e4e0d31438f1b910a79dadc8b2a02c9f9a4ea8c8bd51231022de2f29ec26c6')

    def test_file_payload_has_verified_closure_without_archive(self):
        self.check_package(files_mode=True)

    def check_package(self, selector=None,files_mode=False):
        with tempfile.TemporaryDirectory(prefix='pocket-package-') as temporary:
            root=Path(temporary);commit='1234567890abcdef'*2+'12345678'
            (root/'VERSION').write_text('0.1.0\n')
            files={'build_identity.py':(ROOT/'shell/build_identity.py').read_bytes(),'native/cell_module.c':b'/* original fixture C */','native/cell_engine.c':b'/* original engine */','demo.py':b'# fixture shell\n'}
            for name,raw in files.items():
                path=root/'shell'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            platform=root/'platform/n810';(platform/'registration').mkdir(parents=True)
            for name in ('install.py','session_entry.py','upgrade_session.py','rnode_spp_prepare.py','rnode_spp_prepare.provenance.json'):(platform/name).write_bytes((ROOT/'platform/n810'/name).read_bytes())
            (platform/'registration/register_candidate.py').write_bytes((ROOT/'platform/n810/registration/register_candidate.py').read_bytes())
            baseline=root/'baseline.tar.gz';platform_files={'vendor/native/_cellengine.abi3.so':b'opaque fixture bytes','build-info.json':b'{}',
                'native/build-host/Darwin-arm64-geometry/libgeometry.dylib':b'host-only fixture',
                'vendor/native/libpocket_rns.so':b'fixture native library',
                'vendor/native/libpocket_rns.provenance.json':json.dumps(dict(abi=2,platform='Linux-armv6l',library_sha256=sha(b'fixture native library'))).encode()}
            with tarfile.open(baseline,'w:gz') as archive:
                for name,raw in {**files,**platform_files}.items():
                    entry=tarfile.TarInfo(name);entry.size=len(raw);archive.addfile(entry,io.BytesIO(raw))
            def git(command,**options):
                if command[1]=='status':return b''
                if command[1]=='rev-parse':return commit+'\n'
                if command[1]=='ls-files':return '\n'.join('shell/'+name for name in files)+'\n'
                raise AssertionError(command)
            real_verify=package.verify;calls=[]
            def verify(path):
                calls.append(path)
                return {'engine_sha256':package.BASELINE,'platform_files':list(platform_files)} if len(calls)==1 else real_verify(path)
            arguments=['package','--platform-release',str(baseline)]+(['--files'] if files_mode else [])
            if selector is not None:arguments+=['--selector-sha256',selector]
            with patch.object(package,'ROOT',root),patch.object(package.subprocess,'check_output',side_effect=git),patch.object(package,'verify',side_effect=verify),patch.object(sys,'argv',arguments):package.main()
            output=root/'dist'/('pocket-'+commit[:12]+('-files' if files_mode else ''));receipt=json.loads((output/'INSTALL.json').read_text())
            self.assertEqual(receipt['product_version'],'0.1.0')
            namespace={'__file__':'/missing/build_identity.py'}
            if files_mode:
                self.assertFalse((output/'nokia.tar.gz').exists())
                payload=output/'files';manifest=json.loads((payload/'device-poc/pocket-manifest.json').read_text())
                actual={str(path.relative_to(payload)) for path in payload.rglob('*') if path.is_file()}
                self.assertEqual(actual,set(manifest['files'])|{'device-poc/pocket-manifest.json'})
                self.assertFalse(any(name.startswith('native/build-host/Darwin-') for name in actual))
                for name,digest in manifest['files'].items():self.assertEqual(sha((payload/name).read_bytes()),digest)
                identity=(payload/'build_identity.py').read_bytes()
                self.assertTrue(constants(output/'register_candidate.py',{'FILE_PAYLOAD'})['FILE_PAYLOAD'])
            else:
                with tarfile.open(output/'nokia.tar.gz') as archive:
                    identity=archive.extractfile('build_identity.py').read()
                    self.assertFalse(any(name.startswith('native/build-host/Darwin-') for name in archive.getnames()))
            exec(compile(identity,'build_identity.py','exec'),namespace)
            self.assertEqual(namespace['release_id'](),commit[:12])
            self.assertNotIn('IDENTITY',namespace)
            self.assertEqual(set(receipt['files']),{'register_candidate.py','install.py','session_entry.py','upgrade_session.py','rnode_spp_prepare.py'}| (set() if files_mode else {'nokia.tar.gz'}))
            for name,digest in receipt['files'].items():self.assertEqual(sha((output/name).read_bytes()),digest)
            values=constants(output/'install.py',{'REGISTRAR_SHA256','SESSION_ENTRY_SHA256','SESSION_UPGRADE_SHA256','ENGINE_SHA256'})
            self.assertEqual(values['REGISTRAR_SHA256'],receipt['files']['register_candidate.py'])
            self.assertEqual(values['SESSION_ENTRY_SHA256'],receipt['files']['session_entry.py'])
            self.assertEqual(values['SESSION_UPGRADE_SHA256'],receipt['files']['upgrade_session.py'])
            self.assertEqual(values['ENGINE_SHA256'],receipt['engine'])
            selected=constants(output/'register_candidate.py',{'SELECTOR_SHA'})['SELECTOR_SHA']
            self.assertEqual(selected,receipt['selector_sha256'])
            self.assertEqual(selected,selector or constants(ROOT/'platform/n810/registration/register_candidate.py',{'SELECTOR_SHA'})['SELECTOR_SHA'])
            self.assertEqual(constants(output/'upgrade_session.py',{'CURRENT_SELECTOR'})['CURRENT_SELECTOR'],selector)
            self.assertEqual(len(calls),1 if files_mode else 2)


class RegistrarInputContracts(unittest.TestCase):
    def test_nonregular_registrar_cannot_block_before_validation(self):
        # Exact installer in a separate unprivileged child: only geteuid is
        # mocked. A rejected FIFO must not wait forever for a writer.
        with tempfile.TemporaryDirectory(prefix='pocket-registrar-fifo-') as temporary:
            stage=Path(temporary);os.mkfifo(stage/'register_candidate.py')
            script="""import importlib.util,sys
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('fixture',sys.argv[1]);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.STAGE=Path(sys.argv[2]);sys.argv=['fixture']
with patch.object(module.os,'geteuid',return_value=0):module.main()
"""
            try:child=subprocess.run([sys.executable,'-B','-c',script,str(ROOT/'platform/n810/install.py'),str(stage)],capture_output=True,text=True,timeout=2)
            except subprocess.TimeoutExpired:self.fail('Installer blocks opening a FIFO registrar before its regular-file check; add O_NONBLOCK to the registrar read open')
            self.assertNotEqual(child.returncode,0)


class SppUpgradeTests(unittest.TestCase):
    def exercise(self,case):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);stage=root/'stage';stage.mkdir();receipt=root/'receipt';receipt.mkdir()
            target=root/'helper';target.write_bytes(b'old');target.chmod(0o755)
            payload=b'reviewed helper';(stage/'rnode_spp_prepare.py').write_bytes(payload)
            if case=='same':target.write_bytes(payload)
            if case=='corrupt':(stage/'rnode_spp_prepare.py').write_bytes(b'corrupt')
            if case=='external':target.write_bytes(b'custom')
            before=target.read_bytes();inode=target.stat().st_ino;real_lstat=Path.lstat
            def local_path(value):return target if str(value)=='/usr/local/sbin/n810-rnode-spp-prepare' else Path(value)
            def lstat(path,*args,**kwargs):
                info=real_lstat(path,*args,**kwargs)
                return SimpleNamespace(st_mode=info.st_mode,st_uid=0) if path==target else info
            with patch.object(installer,'STAGE',stage),patch.object(installer,'RECEIPT_DIRECTORY',receipt),patch.object(installer,'SPP_HELPER_SHA256',sha(payload)),patch.object(installer,'SPP_HELPER_PREDECESSORS',(sha(b'old'),)),patch.object(installer,'Path',local_path),patch.object(Path,'lstat',autospec=True,side_effect=lstat),patch.object(installer.os,'chown'):
                if case in ('corrupt','external'):
                    with self.assertRaises(ValueError):installer.upgrade_spp_helper()
                    self.assertEqual(target.read_bytes(),before)
                    self.assertFalse((receipt/'rnode-spp-prepare.before.py').exists())
                else:
                    installer.upgrade_spp_helper();self.assertEqual(target.read_bytes(),payload)
                    if case=='same':self.assertEqual(target.stat().st_ino,inode)
                    else:
                        self.assertEqual((receipt/'rnode-spp-prepare.before.py').read_bytes(),before)
                        self.assertEqual(json.loads((receipt/'SPP_HELPER.json').read_text())['sha256'],sha(payload))
    def test_reviewed_helper_is_replaced_with_rollback(self):self.exercise('upgrade')
    def test_matching_helper_is_not_replaced(self):self.exercise('same')
    def test_corrupt_helper_payload_is_rejected(self):self.exercise('corrupt')
    def test_external_helper_is_not_overwritten(self):self.exercise('external')

if __name__=='__main__':unittest.main()
