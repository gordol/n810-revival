import os
import pathlib
import re
import struct
import subprocess
import tempfile
import time

source = pathlib.Path(__file__).with_name('n810-backlightd.c').read_text()
with tempfile.TemporaryDirectory() as directory:
    root = pathlib.Path(directory)
    inputs = root / 'input'
    inputs.mkdir()
    paths = {'CONFIG_PATH': 'config', 'LED_PATH': 'brightness',
             'LUX_PATH': 'lux', 'BATTERY_PATH': 'capacity',
             'CHARGER_PATH': 'online', 'INPUT_DIR': 'input', 'LOCK_PATH': 'locked'}
    for key, name in paths.items():
        source = re.sub(r'#define ' + key + r' "[^"]+"',
                        '#define ' + key + ' "' + str(root / name) + '"', source)
    # FIFO devices exercise the actual event loop; only evdev identity/state
    # ioctls are substituted. The daemon remains the sole brightness writer.
    wrapper = r'''
#include <stdarg.h>
int mock_ioctl(int fd, unsigned long request, ...) {
    va_list args; va_start(args, request); void *out = va_arg(args, void *); va_end(args);
    char link[64], path[4096] = {0};
    snprintf(link, sizeof(link), "/proc/self/fd/%d", fd);
    if (readlink(link, path, sizeof(path) - 1) < 0) return -1;
    if (_IOC_NR(request) == _IOC_NR(EVIOCGNAME(128))) {
        const char *name = strstr(path, "event0") ? "Internal keyboard" :
                           strstr(path, "event2") ? "gpio-keys" : "N810 internal keyboard";
        snprintf(out, _IOC_SIZE(request), "%s", name); return strlen(name);
    }
    if (_IOC_NR(request) == _IOC_NR(EVIOCGSW(8))) {
        memset(out, 0, _IOC_SIZE(request));
        ((unsigned long *)out)[SW_KEYPAD_SLIDE / (8 * sizeof(long))] |=
            1UL << (SW_KEYPAD_SLIDE % (8 * sizeof(long))); return 0;
    }
    return -1;
}
'''
    source += wrapper
    source = source.replace('#include <sys/ioctl.h>',
                            '#include <sys/ioctl.h>\nint mock_ioctl(int, unsigned long, ...);\n#define ioctl mock_ioctl')
    (root / 'daemon.c').write_text(source)
    (root / 'config').write_text('keyboard_hold_seconds=1\nkeyboard_fade_seconds=1\nkeyboard_idle_seconds=4\n')
    for name, value in [('lux', 20), ('capacity', 90), ('online', 1), ('brightness', 0)]:
        (root / name).write_text(str(value))
    subprocess.run(['gcc', '-Wall', '-Wextra', '-Werror', str(root / 'daemon.c'), '-o', str(root / 'daemon')], check=True)
    fds = []
    def device(number):
        path = inputs / ('event' + str(number))
        os.mkfifo(path)
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        fds.append(fd)
        return fd
    physical = device(0)
    switch = device(2)
    daemon = subprocess.Popen([str(root / 'daemon')])
    def wait_light(lit, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            text = (root / 'brightness').read_text().strip()
            if text and (int(text) > 0) == lit:
                return
            assert daemon.poll() is None, 'daemon exited'
            time.sleep(0.05)
        raise AssertionError('brightness did not become ' + ('lit' if lit else 'off'))
    def event(fd, type_, code, value):
        os.write(fd, struct.pack('@llHHi', 0, 0, type_, code, value))
    try:
        wait_light(True)
        time.sleep(2.3)
        assert int((root / 'brightness').read_text()) == 56, 'idle floor lost'
        wait_light(False)
        virtual = device(3)  # Remapper starts after lamp daemon.
        time.sleep(2.2)
        event(virtual, 1, 30, 1)
        wait_light(True)
        wait_light(False)
        print('PASS: late virtual keyboard wakes lamp and fades')
        (root/'locked').touch();event(virtual,1,30,1)
        wait_light(False)
        event(switch,5,10,1);time.sleep(.3)
        assert int((root/'brightness').read_text())==0, 'locked slide lit keyboard'
        (root/'locked').unlink();wait_light(True)
        print('PASS: lock keeps lamp off; unlock restores open keyboard')
        event(switch, 5, 10, 0)
        time.sleep(0.1)
        event(virtual, 1, 30, 1)
        time.sleep(0.2)
        assert int((root / 'brightness').read_text()) == 0
        event(switch, 5, 10, 1)
        wait_light(True)
        wait_light(False)
        print('PASS: closed slide suppresses typing; opening still wakes lamp')
        os.close(virtual)
        fds.remove(virtual)
        (inputs / 'event3').unlink()
        time.sleep(0.2)
        virtual = device(7)  # Remapper restart with a different event number.
        time.sleep(2.2)
        event(virtual, 1, 30, 1)
        wait_light(True)
        wait_light(False)
        print('PASS: recreated virtual keyboard is rediscovered by name')
        event(physical, 1, 30, 1)
        wait_light(True)
        print('PASS: physical keyboard fallback works')
    finally:
        daemon.terminate()
        daemon.wait(timeout=3)
        for fd in fds:
            os.close(fd)
