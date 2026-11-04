"""Test menu navigation outcomes without invoking real power actions."""
import os
import pathlib
import subprocess
import tempfile
source = pathlib.Path(__file__).with_name('n810-power-menu').read_text()
with tempfile.TemporaryDirectory() as directory:
    root = pathlib.Path(directory)
    for path in ['/usr/local/bin/n810-power', '/usr/local/sbin/n810-screen', '/sbin/shutdown', '/usr/local/sbin/n810-mode', '/usr/local/sbin/n810-radio']:
        source = source.replace(path, str(root / pathlib.Path(path).name))
    (root / 'n810-dialog').write_text(pathlib.Path(__file__).with_name('n810-dialog').read_text()); (root / 'n810-dialog').chmod(0o755)
    (root / 'menu').write_text(source); (root / 'menu').chmod(0o755)
    for name in ['n810-power', 'n810-screen', 'shutdown', 'n810-mode', 'n810-radio']:
        (root / name).write_text('''#!/bin/sh
if test "${1:-}" = status; then echo "Airplane mode ${TEST_AIRPLANE:-off}"; exit 0; fi
if test "${1:-}" = --tmux; then echo 'N810 75% 4.038V CHARGING'; exit 0; fi
printf '%s %s\n' "$(basename "$0")" "$*" >> "$TEST_ACTIONS"
''')
    (root / 'id').write_text('#!/bin/sh\necho 1000\n')
    (root / 'sudo').write_text('''#!/bin/sh
test "$1" = -n || exit 2
shift
exec "$@"
''')
    (root / 'whiptail').write_text('''#!/bin/sh
printf '%s\n' "$*" >> "$TEST_DIALOGS"
case "$*" in
 *--yesno*) test "$TEST_CONFIRM" = yes; exit $?;;
 *--msgbox*) exit 0;;
esac
choice=$(head -n 1 "$TEST_CHOICES")
sed '1d' "$TEST_CHOICES" > "$TEST_CHOICES.next"
mv "$TEST_CHOICES.next" "$TEST_CHOICES"
test "$choice" != cancel || exit 255
printf '%s\n' "$choice" >&2
''')
    for name in ['n810-power', 'n810-screen', 'shutdown', 'n810-mode', 'n810-radio', 'id', 'sudo', 'whiptail']:
        (root / name).chmod(0o755)
    env = dict(os.environ, PATH=str(root)+':'+os.environ['PATH'],
               TEST_ACTIONS=str(root/'actions'), TEST_DIALOGS=str(root/'dialogs'),
               TEST_CHOICES=str(root/'choices'))
    def check(choices, confirm, expected, airplane="off"):
        (root/'actions').write_text(''); (root/'dialogs').write_text('')
        (root/'choices').write_text('\n'.join(choices)+'\n')
        subprocess.run([str(root/'menu')], env=dict(env,TEST_CONFIRM=confirm,TEST_AIRPLANE=airplane), check=True)
        assert (root/'actions').read_text().splitlines() == expected
        dialogs = (root/'dialogs').read_text()
        assert '--default-item back' in dialogs and '--cancel-button Back' in dialogs
        if 'shutdown' in choices:
            assert '--defaultno' in dialogs
    check(['cancel'], 'no', [])
    check(['back'], 'no', [])
    check(['topoff', 'longevity', 'back'], 'no', ['n810-power topoff','n810-power longevity'])
    check(['off'], 'no', ['n810-screen off'])
    check(['on'], 'no', ['n810-screen on'])
    check(['auto','back'], 'no', ['n810-screen auto'])
    check(['radios', 'back'], 'no', ['n810-radio airplane-on'])
    check(['radios', 'back'], 'no', ['n810-radio airplane-off'], airplane='on')
    check(['quiet'], 'no', ['n810-mode charging'])
    check(['shutdown', 'back'], 'no', [])
    check(['shutdown'], 'yes', ['shutdown -h now'])
print('PASS: menu cancellation, fixed actions, sudo noninteractive, default-safe shutdown confirmation')
