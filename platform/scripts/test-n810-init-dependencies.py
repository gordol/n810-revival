"""Generate a real SysV startup graph; check the hook is scheduled after inputs/Wi-Fi."""
import os
from pathlib import Path
import subprocess
import tempfile
repo=Path(__file__).resolve().parents[1]
insserv=os.environ.get('N810_INSSERV','insserv')
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    init=root/'etc/init.d'; init.mkdir(parents=True)
    for level in ('S','0','1','2','3','4','5','6'): (root/f'etc/rc{level}.d').mkdir()
    overrides=root/'overrides'; overrides.mkdir()
    upstart=root/'upstart'; upstart.mkdir()
    config=root/'insserv.conf'; config.write_text('$local_fs local\n')
    def service(name, requires, levels):
        path=init/name
        path.write_text(f'''#!/bin/sh
### BEGIN INIT INFO
# Provides: {name}
# Required-Start: {requires}
# Required-Stop: $local_fs
# Default-Start: {levels}
# Default-Stop: 0 1 6
### END INIT INFO
exit 0
'''); path.chmod(0o755)
    service('local','','S')
    service('n810-console-ux','$local_fs','2 3 4 5')
    service('n810-wake','n810-console-ux','2 3 4 5')
    for name in ('n810-wifi','n810-backlightd'): service(name,'$local_fs','2 3 4 5')
    hook=init/'n810-boot-mode'; hook.write_bytes((repo/'device/n810-boot-mode.init').read_bytes()); hook.chmod(0o755)
    command=[insserv,'-p',str(init),'-c',str(config),'-o',str(overrides),'-u',str(upstart),'-i',str(init)]
    subprocess.run(command+['-d','-e','n810-boot-mode'],check=True)
    graph=(init/'.depend.start').read_text()
    assert 'n810-boot-mode' in next(line for line in graph.splitlines() if line.startswith('TARGETS ='))
    dependencies=next(line for line in graph.splitlines() if line.startswith('n810-boot-mode:')).split()[1:]
    assert {'n810-wake','n810-wifi','n810-backlightd'} <= set(dependencies), dependencies
    for level in ('2','3','4','5'):
        links=list((root/f'etc/rc{level}.d').glob('S*n810-boot-mode'))
        assert len(links)==1 and links[0].is_symlink()
    print('PASS: real insserv graph schedules boot mode after wake/backlight/Wi-Fi in runlevels 2–5')
