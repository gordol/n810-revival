import os
import pty
import subprocess
import time

socket = 'n810-resize-check-' + str(os.getpid())
def tmux(*args):
    return subprocess.check_output(['tmux', '-L', socket, *args], text=True).strip()

master = slave = None
client = None
try:
    tmux('-f', '/dev/null', 'new-session', '-d', '-s', 'test', '-x', '100', '-y', '30')
    tmux('set-option', '-g', 'prefix', 'S-F1')
    tmux('set-option', '-g', 'status', 'off')
    tmux('split-window', '-h')
    tmux('select-pane', '-t', 'test:0.0')
    tmux('bind-key', 'Right', 'select-pane', '-R')
    master, slave = pty.openpty()
    import fcntl, termios, struct
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
    client = subprocess.Popen(['tmux', '-L', socket, 'attach-session', '-t', 'test'],
                              stdin=slave, stdout=slave, stderr=slave,
                              env=dict(os.environ, TERM='linux'))
    time.sleep(1)
    for name, seq in [('Right', b'\x1b[1;5C'), ('Left', b'\x1b[1;5D'),
                      ('Up', b'\x1b[1;5A'), ('Down', b'\x1b[1;5B')]:
        if name == 'Up':
            tmux('kill-pane', '-t', 'test:0.1')
            tmux('split-window', '-v')
            tmux('select-pane', '-t', 'test:0.0')
        before = tmux('display-message', '-p', '#{pane_id}:#{pane_width}:#{pane_height}')
        os.write(master, b'\x1b[25~' + seq)
        time.sleep(.3)
        after = tmux('display-message', '-p', '#{pane_id}:#{pane_width}:#{pane_height}')
        assert before.split(':')[0] == after.split(':')[0], (name, before, after)
        assert before != after, (name, before, after)
        print('Ctrl+' + name + ': recognized without changing selected pane', before, after)
    tmux('bind-key', 'Down', 'select-pane', '-D')
    os.write(master, b'\x1b[25~\x1b[B')
    time.sleep(.3)
    assert tmux('display-message', '-p', '#{pane_index}') == '1'
    print('Plain Down: still selects adjacent pane')
finally:
    subprocess.run(['tmux', '-L', socket, 'kill-server'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if client:
        client.wait(timeout=5)
    for fd in (master, slave):
        if fd is not None:
            os.close(fd)
