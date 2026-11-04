"""Exercise real poll/input transitions with FIFO evdev identity substitution."""
import os
import pathlib
import struct
import subprocess
import tempfile
import time

source = pathlib.Path(__file__).with_name('n810-wake.c').read_text()
with tempfile.TemporaryDirectory() as directory:
    root = pathlib.Path(directory)
    (root / 'input').mkdir()
    (root / 'screen').mkdir()
    for key, path in [('INPUT_GLOB', root / 'input/event*'), ('CONFIG_PATH', root / 'config'),
                      ('SCREEN_DIR', root / 'screen'), ('SCREEN_COMMAND', root / 'screen-command'),
                      ('MENU_COMMAND', root / 'menu-command'), ('MODE_COMMAND', root / 'mode-command'), ('ACTIVE_VT_PATH', root / 'active-vt'),
                      ('GPIO_GLOB', root / 'gpiochip*'), ('LOCK_FIFO', root / 'lock-input')]:
        source = '#define ' + key + ' "' + str(path) + '"\n' + source
    source = source.replace('#include <sys/ioctl.h>',
        '#include <sys/ioctl.h>\nint mock_ioctl(int, unsigned long, ...);\n#define ioctl mock_ioctl')
    source += r'''
#include <stdarg.h>
int mock_ioctl(int fd, unsigned long request, ...) {
    va_list args; va_start(args, request); void *out = va_arg(args, void *); va_end(args);
    if(request == GPIO_GET_CHIPINFO_IOCTL) {
        struct gpiochip_info *chip=out;
        strcpy(chip->label,"gpio-96-127");return 0;
    }
    if(request == GPIO_GET_LINEEVENT_IOCTL) {
        struct gpioevent_request *edge=out;
        if(edge->lineoffset!=6 || edge->handleflags!=GPIOHANDLE_REQUEST_INPUT ||
           edge->eventflags!=GPIOEVENT_REQUEST_BOTH_EDGES) return -1;
        edge->fd=open(LOCK_FIFO,O_RDONLY|O_NONBLOCK);return edge->fd<0?-1:0;
    }
    if(request == KDGETMODE) {
        char value[8]={0};
        if(read(fd,value,sizeof(value)-1)<0) return -1;
        *(int *)out=atoi(value);return 0;
    }
    char link[64], path[4096] = {0};
    snprintf(link, sizeof(link), "/proc/self/fd/%d", fd);
    if (readlink(link, path, sizeof(path) - 1) < 0) return -1;
    if (_IOC_NR(request) == 0x20 + EV_KEY) {
        unsigned long *keys = out;
        memset(out, 0, _IOC_SIZE(request));
        if (strstr(path, "event5")) {
            unsigned bits = sizeof(unsigned long) * 8;
            keys[KEY_A / bits] |= 1UL << (KEY_A % bits);
            keys[KEY_ENTER / bits] |= 1UL << (KEY_ENTER % bits);
        }
        return 0;
    }
    const char *name = strstr(path, "event0") ? "Internal keyboard" :
                       strstr(path, "event1") ? "retu-pwrbutton" :
                       strstr(path, "event2") ? "gpio-keys" :
                       strstr(path, "event4") ? "TSC2005 touchscreen" :
                       strstr(path, "event5") ? "External test keyboard" : "N810 internal keyboard";
    snprintf(out, _IOC_SIZE(request), "%s", name); return strlen(name);
}
'''
    (root / 'test.c').write_text(source)
    subprocess.run(['gcc', '-Wall', '-Wextra', '-Werror', str(root / 'test.c'), '-o', str(root / 'daemon')], check=True)
    (root / 'config').write_text('enabled=1\nidle_enabled=1\ndim_seconds=2\noff_seconds=4\n')
    (root / 'screen-command').write_text(f'''#!/bin/sh
set -eu
echo "$1" >> '{root}/actions'
case "$1" in
 lock) touch '{root}/screen/locked' '{root}/screen/blanked' '{root}/screen/hold';;
 unlock) rm -f '{root}/screen/locked' '{root}/screen/blanked' '{root}/screen/hold';;
 off) touch '{root}/screen/blanked' '{root}/screen/hold';;
 dim) touch '{root}/screen/idle-percent';;
 blank) touch '{root}/screen/blanked';;
 on) rm -f '{root}/screen/idle-percent' '{root}/screen/blanked' '{root}/screen/hold';;
esac
''')
    (root / 'menu-command').write_text(f"#!/bin/sh\necho menu >> '{root}/actions'\n")
    (root / 'mode-command').write_text(f"#!/bin/sh\necho mode-$1 >> '{root}/actions'\nrm -f '{root}/screen/quiet-charging'\n")
    for name in ['screen-command', 'menu-command', 'mode-command']:
        (root / name).chmod(0o755)
    (root / 'actions').touch()
    (root/'gpiochip0').touch()
    os.mkfifo(root/'lock-input')
    lock_fd=os.open(root/'lock-input',os.O_RDWR|os.O_NONBLOCK)
    fds = []
    def device(number):
        path = root / 'input' / ('event' + str(number))
        os.mkfifo(path)
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        fds.append(fd)
        return fd
    physical, power, switch = [device(i) for i in range(3)]
    daemon = subprocess.Popen([str(root / 'daemon')])
    def event(fd, type_, code, value):
        os.write(fd, struct.pack('@llHHi', 0, 0, type_, code, value))
    def actions():
        return (root / 'actions').read_text().splitlines()
    def wait(action, seconds=6):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if actions() and actions()[-1] == action:
                return
            assert daemon.poll() is None, 'daemon exited'
            time.sleep(.05)
        raise AssertionError(f'Expected {action}, got {actions()}')
    def clear():
        (root / 'actions').write_text('')
    def power_press(duration=.1):
        event(power, 1, 116, 1)
        time.sleep(duration)
        event(power, 1, 116, 0)
    try:
        wait('dim'); wait('blank')
        virtual = device(3)
        time.sleep(2.2)
        event(virtual, 1, 30, 1)
        wait('on')
        print('PASS: dim/off deadlines and late remapped-keyboard wake')
        external = device(5)
        time.sleep(2.2)
        wait('blank')
        event(external, 1, 30, 1); wait('on')
        clear()
        (root/'screen/locked').touch()
        (root/'screen/blanked').touch()
        event(external, 1, 30, 1); time.sleep(.3)
        assert not actions(), 'external keyboard woke locked screen'
        (root/'screen/locked').unlink()
        event(external, 1, 30, 1); wait('on')
        print('PASS: external keyboard hotplug wakes blank screen and respects slider lock')
        clear()
        def lock_edge(value):
            os.write(lock_fd,struct.pack('@QI4x',time.monotonic_ns(),value))
        def lock_press():
            lock_edge(2);time.sleep(.1);lock_edge(1)
        # Contact bounce at both ends of a held press must toggle just once.
        lock_edge(2);time.sleep(.01);lock_edge(1);time.sleep(.01)
        lock_edge(2);time.sleep(.12)
        wait('lock')
        assert actions()==['lock'], 'held slider toggled more than once'
        lock_edge(1);time.sleep(.01);lock_edge(2);time.sleep(.01);lock_edge(1)
        wait('lock'); clear()
        # Short release chatter must not count as a fresh press.
        lock_edge(2);time.sleep(.01);lock_edge(1)
        event(virtual,1,30,1); event(switch,5,10,1)
        event(virtual,1,225,1); time.sleep(.3)
        assert not actions(), 'locked input or bounce changed display'
        power_press(); wait('on'); clear()
        assert (root/'screen/locked').exists(), 'Power cleared lock'
        event(virtual,1,30,1);time.sleep(.2)
        assert not actions(), 'locked key woke display or opened menu'
        power_press();wait('off');clear()
        # A complete press queued during blocking display work still counts.
        base=time.monotonic_ns()-500_000_000
        os.write(lock_fd,struct.pack('@QI4x',base,2)+struct.pack('@QI4x',base+150_000_000,1))
        wait('unlock')
        assert not (root/'screen/locked').exists()
        print('PASS: spring-slider press/release debounce, locked input, Power display toggle, unlock')
        (root / 'screen/hold').touch(); (root / 'screen/blanked').touch()
        clear(); event(virtual, 1, 30, 1); time.sleep(.5)
        wait('on')
        (root / 'screen/hold').touch(); (root / 'screen/blanked').touch()
        clear(); power_press(); wait('on')
        clear(); power_press(); wait('menu')
        print('PASS: screen-off input wake, power wake and menu')
        (root/'screen/quiet-charging').touch(); clear()
        event(virtual,1,30,1); event(switch,5,10,1); lock_press()
        time.sleep(.3)
        assert not actions(), 'ordinary input woke quiet mode'
        power_press(1.6); time.sleep(.2)
        assert not actions(), 'long Power press exited quiet mode'
        power_press(); wait('mode-normal'); clear()
        print('PASS: quiet charging ignores keys/slider; short Power returns to normal')
        clear(); power_press(1.6); time.sleep(.2)
        assert 'menu' not in actions(), 'long press opened menu'
        wait('blank')
        clear(); event(switch, 5, 2, 1); time.sleep(.5)
        assert not actions(), 'headphone insertion woke LCD'
        event(switch, 5, 10, 1); wait('on')
        print('PASS: long press ignored; only keyboard-slide opening wakes')
        clear(); os.close(virtual); fds.remove(virtual)
        (root / 'input/event3').unlink()
        wait('blank')
        virtual = device(7); time.sleep(2.2)
        event(virtual, 1, 30, 1); wait('on')
        print('PASS: restarted remapper rediscovered by identity')
    finally:
        daemon.terminate(); daemon.wait(timeout=3)
        for fd in fds: os.close(fd)
    (root/'config').write_text('enabled=1\nidle_enabled=0\ndim_seconds=1\noff_seconds=2\n')
    for path in (root/'input').iterdir(): path.unlink()
    fds=[]
    power=device(1)
    for path in (root/'screen').iterdir(): path.unlink()
    clear()
    daemon=subprocess.Popen([str(root/'daemon')])
    try:
        time.sleep(3)
        assert not actions(), 'button-only mode invoked idle display action'
        (root/'screen/blanked').touch()
        physical=device(0); time.sleep(2.2)
        event(physical,1,30,1); wait('on'); clear()
        power_press(); wait('menu')
        virtual=device(3); time.sleep(2.2); clear()
        event(virtual,1,225,1); wait('brighter'); clear()
        event(virtual,1,224,1); wait('dimmer')
        print('PASS: brightness keys handled in button-only mode')
        print('PASS: button-only mode opens menu without automatic dim/blank')
    finally:
        daemon.terminate(); daemon.wait(timeout=3)
        for fd in fds: os.close(fd)

    for slide_enabled in [1,0]:
        (root/'config').write_text(f'enabled=1\nidle_enabled=0\nkeyboard_wake=0\nslide_wake={slide_enabled}\ndim_seconds=1\noff_seconds=2\n')
        for path in (root/'input').iterdir(): path.unlink()
        fds=[]
        physical,power,switch=[device(i) for i in range(3)]
        clear(); (root/'screen/blanked').touch()
        daemon=subprocess.Popen([str(root/'daemon')])
        try:
            time.sleep(.3)
            assert (root/'screen/power-only').exists()
            event(physical,1,30,1); time.sleep(.3)
            assert not actions(), 'disabled keyboard woke screen'
            event(switch,5,10,1)
            if slide_enabled: wait('on')
            else:
                time.sleep(.3); assert not actions(), 'disabled slide woke screen'
            clear(); (root/'screen/blanked').touch()
            power_press(); wait('on')
            print(f'PASS: keyboard wake off, slide wake {slide_enabled}, Power still wakes')
        finally:
            daemon.terminate(); daemon.wait(timeout=3)
            assert not (root/'screen/power-only').exists()
            for fd in fds: os.close(fd)

    (root/'config').write_text('enabled=1\nidle_enabled=1\ndim_seconds=1\noff_seconds=2\n')
    (root/'active-vt').write_text('1')  # KD_GRAPHICS
    for path in (root/'screen').iterdir(): path.unlink()
    clear()
    daemon=subprocess.Popen([str(root/'daemon')])
    try:
        time.sleep(3.2)
        assert not actions(), 'graphics VT was dimmed or blanked'
        (root/'active-vt').write_text('0')  # KD_TEXT
        wait('dim'); wait('blank')
        print('PASS: graphics VT inhibits idle; text VT resumes dim/blank')
    finally:
        daemon.terminate(); daemon.wait(timeout=3)

    # An explicit GUI adapter marker enables the same policy on graphics VTs.
    (root/'active-vt').write_text('1')
    for path in (root/'input').iterdir(): path.unlink()
    fds=[]
    physical,power,switch=[device(i) for i in range(3)]
    touch=device(4)
    for path in (root/'screen').iterdir(): path.unlink()
    (root/'screen/x11-managed').touch()
    clear()
    daemon=subprocess.Popen([str(root/'daemon')])
    try:
        time.sleep(.3)
        lock_press(); wait('lock'); clear()
        event(physical,1,30,1); event(switch,5,10,1);time.sleep(.3)
        assert not actions(), 'locked GUI input changed display'
        power_press();wait('on');clear()
        assert (root/'screen/locked').exists(), 'GUI Power cleared lock'
        lock_press();wait('unlock');clear()
        event(physical,1,225,1);wait('brighter');clear()
        power_press();wait('menu');clear()
        wait('dim');wait('blank')
        clear();event(touch,1,330,1);time.sleep(.2)
        assert not actions(), 'touch woke a blank GUI'
        power_press();wait('on');clear()
        for _ in range(6):
            event(touch,1,330,1);event(touch,1,330,0);time.sleep(.4)
        assert not actions(), 'active touch use did not inhibit idle dim/off'
        print('PASS: managed GUI shares slider, Power, brightness, idle; touch keeps it active without waking')
    finally:
        daemon.terminate();daemon.wait(timeout=3)
        for fd in fds:os.close(fd)
