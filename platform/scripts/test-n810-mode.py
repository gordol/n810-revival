"""Test service/display transitions without touching hardware."""
import os
from pathlib import Path
import subprocess
import tempfile

helper = Path(__file__).with_name('n810-mode').resolve()
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    for name in ('screen', 'state', 'init'): (root/name).mkdir()
    (root/'online').write_text('1\n')
    (root/'init/n810-wake').write_text('#!/bin/sh\nexit 0\n')
    (root/'init/n810-wake').chmod(0o755)
    for name in ('n810-backlightd', 'n810-displayd', 'n810-wifi', 'chrony'):
        script = root/'init'/name
        script.write_text(f'''#!/bin/sh
set -eu
root='{root}'
name={name}
case "$1" in
status) test ! -e "$root/unknown" || exit 1; test -e "$root/$name.active" || exit 3;;
stop) echo "$name stop" >> "$root/actions"; test ! -e "$root/fail-stop" || exit 1; rm -f "$root/$name.active";;
start) echo "$name start" >> "$root/actions"; test ! -e "$root/fail-start" || exit 1; touch "$root/$name.active";;
esac
''')
        script.chmod(0o755)
        (root/(name+'.active')).touch()
    screen = root/'screen-command'
    screen.write_text(f'''#!/bin/sh
set -eu
echo "screen $1" >> '{root}/actions'
case "$1" in
off) touch '{root}/screen/hold' '{root}/screen/blanked';;
on) rm -f '{root}/screen/hold' '{root}/screen/blanked';;
esac
''')
    screen.chmod(0o755)
    env = dict(os.environ, N810_MODE_SCREEN_DIR=str(root/'screen'), N810_MODE_STATE_DIR=str(root/'state'),
               N810_MODE_INIT_DIR=str(root/'init'), N810_MODE_SCREEN_COMMAND=str(screen), N810_MODE_ONLINE=str(root/'online'))
    def run(action, success=True):
        result = subprocess.run([str(helper), action], env=env, capture_output=True, text=True)
        assert (result.returncode == 0) == success, (action, result.stdout, result.stderr)
        return result.stdout
    def quiet(): return (root/'screen/quiet-charging').exists()
    assert run('status') == 'normal\n'
    (root/'online').write_text('0\n'); run('charging', False); assert not quiet()
    (root/'online').write_text('1\n')
    (root/'unknown').touch(); run('charging', False); assert not quiet()
    (root/'unknown').unlink()
    run('charging'); assert quiet() and not (root/'n810-wifi.active').exists()
    before=(root/'actions').read_text(); run('charging'); assert (root/'actions').read_text() == before
    run('normal'); assert not quiet() and (root/'n810-wifi.active').exists() and not (root/'screen/blanked').exists()
    (root/'n810-wifi.active').unlink(); (root/'screen/locked').touch()
    run('charging'); run('normal')
    assert not (root/'n810-wifi.active').exists() and (root/'screen/blanked').exists()
    for name in ('locked', 'blanked', 'hold'): (root/'screen'/name).unlink()
    (root/'screen/blanked').touch(); (root/'screen/hold').touch()
    run('charging'); run('normal'); assert not (root/'screen/blanked').exists()
    (root/'fail-stop').touch(); run('charging', False); assert not quiet()
    (root/'fail-stop').unlink()
    run('charging'); (root/'fail-start').touch(); run('normal', False); assert quiet()
    (root/'fail-start').unlink(); run('normal'); assert not quiet()
    print('PASS: charger required, status errors, idempotency, selective restoration, lock preservation, entry rollback and failed-restore retry')
