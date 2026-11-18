"""Install shared radio code and offline optional runtimes into a fresh build root."""
from pathlib import Path
import os
import hashlib
import json
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def checked_environments(root):
    for name in ('opt/n810-mesh/bin/python', 'opt/pocket-htit/bin/python',
                 'usr/local/share/pocket/shell/vendor/native/libpocket_rns.so',
                 'usr/local/share/pocket/shell/vendor/native/libpocket_rns.provenance.json'):
        if not (Path(root) / name).is_file():
            raise ValueError('Missing optional-service runtime in build root: ' + name)


def stage(root):
    root = Path(root)
    checked_environments(root)
    data_tool=root/'usr/local/bin/n810-install-reference-data'
    data_tool.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(REPO/'pocket/tools/install_reference_data.py',data_tool)
    data_tool.chmod(0o755)
    shell = root / 'usr/local/share/pocket/shell'
    destination = root / 'usr/local/lib/n810-radio'
    destination.mkdir(parents=True, exist_ok=True)
    # The owner implementation overrides the older console dependencies.
    for source in (shell / 'vendor/packet-console', shell / 'owner-service'):
        if not source.is_dir():
            raise ValueError('Missing shared radio source: ' + str(source))
        for path in source.glob('*.py'):
            if path.name.startswith(('test-', 'test_')):
                continue
            target = destination / path.name
            shutil.copyfile(path, target)
            target.chmod(0o644)
    for name in ('peripheral_setup.py', 'service_policy.py', 'optional_services.py'):
        shutil.copyfile(shell / name, destination / name)
    import importlib.util
    schema = destination / 'n810-directory-model.py'
    spec = importlib.util.spec_from_file_location('first_install_directory', schema)
    model = importlib.util.module_from_spec(spec); spec.loader.exec_module(model)
    state = root / 'home/nokia/.local/state/n810-aprs'
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    database = state / 'directory.sqlite3'
    model.database(database).close()
    account = (root / 'home/nokia').stat()
    for path in (state.parent.parent, state.parent, state, database):
        os.chown(path, account.st_uid, account.st_gid)
    for path in destination.iterdir():
        if path.is_file():path.chmod(0o644)
    destination.chmod(0o755)
    subprocess.run(['chroot', str(root), 'usermod' , '-aG', 'dialout,bluetooth,audio', 'nokia'], check=True)
    for name in ('n810-audio', 'n810-bluetooth-address', 'n810-bluetooth', 'n810-setup-wifi', 'n810-rnode-configure', 'n810-rnode-spp-prepare'):
        target = root / 'usr/local/sbin' / name
        shutil.copyfile(REPO / 'platform/scripts' / name, target)
        target.chmod(0o755)
    module_config = root / 'etc/modprobe.d/n810-bluetooth.conf'
    module_config.parent.mkdir(parents=True, exist_ok=True)
    module_config.write_text('install hci_nokia /usr/local/sbin/n810-bluetooth-address --load-driver\n')
    helpers = root / 'usr/local/lib/n810-setup'
    helpers.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / 'setup_profile.py', helpers / 'setup_profile.py')
    sudoers = root / 'etc/sudoers.d/n810-setup-wifi'
    sudoers.write_text('nokia ALL=(root) NOPASSWD: NOSETENV: /usr/local/sbin/n810-setup-wifi --stdin\n')
    sudoers.chmod(0o440)
    subprocess.run(['chroot', str(root), 'visudo', '-cf', '/etc/sudoers.d/n810-setup-wifi'], check=True)
    platform_lib = root / 'usr/local/lib/n810-platform'
    platform_lib.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / 'pocket/platform/n810/rnode_spp_prepare.py', platform_lib / 'rnode_spp_prepare.py')
    platform_lib.chmod(0o755)
    (platform_lib / 'rnode_spp_prepare.py').chmod(0o644)
    for group, policy in (('n810-power', 'n810-power.sudoers'), ('n810-radio', 'n810-rnode.sudoers')):
        subprocess.run(['chroot', str(root), 'groupadd', '-f', group], check=True)
        subprocess.run(['chroot', str(root), 'usermod', '-aG', group, 'nokia'], check=True)
        target = root / 'etc/sudoers.d' / group
        shutil.copyfile(REPO / 'platform/device' / policy, target)
        target.chmod(0o440)
        subprocess.run(['chroot', str(root), 'visudo', '-cf', '/etc/sudoers.d/' + group], check=True)
    bluetooth_defaults = root / 'etc/default/bluetooth'
    text = bluetooth_defaults.read_text() if bluetooth_defaults.exists() else ''
    gate = 'if test -e /var/lib/n810-radio/airplane; then BLUETOOTH_ENABLED=0; fi'
    if gate not in text:bluetooth_defaults.write_text(text + '\n# Persistent radio policy, also for direct SysV starts.\n' + gate + '\n')
    bluetooth_defaults.chmod(0o644)
    return destination


def adapt_meshcore_debian(root):
    """Use Debian's Cryptodome namespace in the locked MeshCore distribution.

    Debian ships pycryptodome as Cryptodome to avoid the obsolete PyCrypto
    namespace. Keep this adaptation local to MeshCore, with before/after hashes.
    """
    matches = list((Path(root) / 'opt/pocket-htit/lib').glob('python*/site-packages/meshcore'))
    if len(matches) != 1:
        raise ValueError('Expected one installed MeshCore package')
    package = matches[0]
    changes = {'meshcore_parser.py': ('from Crypto.Cipher import AES',
                                    'from Crypto.Hash import HMAC, SHA256'),
               'reader.py': ('from Crypto.Hash import SHA256',)}
    prepared = []
    for name, imports in changes.items():
        path = package / name
        before = path.read_bytes()
        text = before.decode('utf-8')
        for line in imports:
            if text.splitlines().count(line) != 1:
                raise ValueError('MeshCore crypto imports changed: ' + name)
            text = text.replace(line, line.replace('from Crypto.', 'from Cryptodome.'))
        prepared.append((path, before, text.encode('utf-8')))
    records = {}
    for path, before, after in prepared:
        path.write_bytes(after)
        records[path.name] = {'upstream_sha256': hashlib.sha256(before).hexdigest(),
                              'installed_sha256': hashlib.sha256(after).hexdigest()}
    (package.parent / 'n810-meshcore-debian.json').write_text(json.dumps({
        'adaptation': 'Debian pycryptodome Cryptodome namespace', 'files': records
    }, indent=2) + '\n')


def environments(root, wheels=Path('/build/service-wheels'), requirements=Path('/build/requirements')):
    """Run in the Linux source builder; never install software on a live tablet."""
    root = Path(root)
    target = root / 'opt/n810-service-wheels'
    shutil.copytree(wheels, target)
    shutil.copytree(requirements, target / 'requirements')
    emulator = root / 'usr/bin/qemu-arm-static'
    owned = not emulator.exists()
    if owned:
        shutil.copyfile('/usr/bin/qemu-arm-static', emulator)
        emulator.chmod(0o755)
    try:
        for directory, lock in (('/opt/n810-mesh', 'n810-mesh-requirements.txt'),
                                ('/opt/pocket-htit', 'n810-meshcore-requirements.txt')):
            subprocess.run(['chroot', str(root), 'python3', '-m', 'venv', '--system-site-packages', directory], check=True)
            subprocess.run(['chroot', str(root), directory + '/bin/pip', 'install',
                            '--no-index', '--only-binary=:all:', '--no-deps', '--require-hashes',
                            '--find-links=/opt/n810-service-wheels', '-r',
                            '/opt/n810-service-wheels/requirements/' + lock], check=True)
        adapt_meshcore_debian(root)
        for directory, imports in (('/opt/n810-mesh', 'import RNS,LXMF,urwid,qrcode,serial,cryptography'),
                                   ('/opt/pocket-htit', 'import meshcore,serial_asyncio_fast,cayennelpp,bleak,Cryptodome; from Cryptodome.Cipher import AES; assert AES.new(bytes(16), AES.MODE_ECB).encrypt(bytes(16)).hex() == "66e94bd4ef8a2c3b884cfa59ca342b2e"')):
            subprocess.run(['chroot', str(root), directory + '/bin/python', '-c', imports], check=True)
    finally:
        if owned:
            emulator.unlink()
        shutil.rmtree(target)
