"""A stalled optional LED service must not delay the Power menu."""
import pathlib, subprocess, tempfile, time
source = pathlib.Path(__file__).with_name('n810-console-power-menu').read_text()
with tempfile.TemporaryDirectory() as directory:
    root = pathlib.Path(directory)
    for name, body in {'led': 'sleep 5', 'console': 'echo 1', 'menu': 'echo MENU_READY'}.items():
        path = root / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755)
    source = source.replace('/usr/local/bin/n810-ledctl', str(root/'led'))
    source = source.replace('$(fgconsole)', '$("' + str(root/'console') + '")')
    source = source.replace('exec openvt', 'exec "' + str(root/'menu') + '"')
    script = root/'dispatch'
    script.write_text(source)
    for available in (True, False):
        if not available:
            (root/'led').unlink()
        start = time.monotonic()
        result = subprocess.run(['sh', str(script)], capture_output=True, text=True, timeout=2)
        assert result.returncode == 0 and result.stdout.strip() == 'MENU_READY', result
        assert time.monotonic() - start < 0.5, 'Optional acknowledgement delayed menu'
    # Allow GNU timeout to reap the bounded acknowledgement process before cleanup.
    time.sleep(1.2)
print('PASS: stalled and missing LED feedback never block menu dispatch.')
