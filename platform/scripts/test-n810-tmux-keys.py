"""Drive real tmux clients: external prefixes and internal Menu must coexist."""
import os, pathlib, pty, select, subprocess, tempfile, time
config = pathlib.Path(__file__).resolve().parent.parent/'config/tmux-n810.conf'
socket = 'n810-keys-test-'+str(os.getpid())
master, slave = pty.openpty()
env = dict(os.environ, TERM='xterm-256color')
client = None

def tmux(*args):
    return subprocess.check_output(['tmux','-L',socket,*args], text=True, env=env).strip()

def drain():
    while select.select([master], [], [], 0)[0]:
        try: os.read(master, 65536)
        except OSError: break

def until(check):
    deadline = time.monotonic()+4
    while time.monotonic()<deadline:
        drain()
        if check(): return
        time.sleep(.05)
    raise AssertionError('Key sequence did not produce the expected tmux action')

def keys(value):
    os.write(master, value)

try:
    tmux('-f',str(config),'new-session','-d','-s','keys','-n','one','-x','100','-y','30')
    client = subprocess.Popen(['tmux','-L',socket,'attach-session','-t','keys'], stdin=slave,stdout=slave,stderr=slave,env=env)
    until(lambda: bool(tmux('list-clients','-F','#{client_name}')))
    for sequence, count in ((b'`c',2),(b'\x02c',3),(b'\x1b[1;2Pc',4)):
        keys(sequence)
        until(lambda: len(tmux('list-windows','-F','#{window_id}').splitlines())==count)
    keys(b'\x1b[1;2Ph')
    until(lambda: len(tmux('list-panes','-F','#{pane_id}').splitlines())==2)
    panes=tmux('list-panes','-F','#{pane_id}').splitlines()
    tmux('select-pane','-t',panes[1])
    keys(b'\x1b[1;2P\x1b[D')
    until(lambda: tmux('display-message','-p','#{pane_id}')==panes[0])
    # Finish the internal navigation repeat window before changing input mode.
    time.sleep(.65)
    width=int(tmux('display-message','-p','#{pane_width}'))
    keys(b'`\x1b[C')
    until(lambda: int(tmux('display-message','-p','#{pane_width}'))>width)
    keys(b'\x1b[1;3C')
    until(lambda: tmux('display-message','-p','#{pane_id}')==panes[1])
    index=tmux('display-message','-p','#{window_index}')
    keys(b'\x1b[1;2D')
    until(lambda: tmux('display-message','-p','#{window_index}')!=index)
    keys(b'`\x1b')
    until(lambda: tmux('display-message','-p','#{pane_in_mode}')=='1')
    keys(b'q')
    until(lambda: tmux('display-message','-p','#{pane_in_mode}')=='0')
    assert 'paste-buffer' in tmux('list-keys','-T','prefix','p')
    assert 'copy-selection-and-cancel' in tmux('list-keys','-T','copy-mode-vi','y')
    assert 'swap-window' in tmux('list-keys','-T','prefix','>')
    print('PASS: backtick, C-b and Menu create windows; Menu arrows select; external prefix arrows resize; Alt arrows select; Shift arrows change windows; Escape copy mode.')
finally:
    subprocess.run(['tmux','-L',socket,'kill-server'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if client is not None: client.wait(timeout=3)
    os.close(master);os.close(slave)
