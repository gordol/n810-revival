# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the actual graphical desktop, app lifecycle and resize boundaries."""
from pathlib import Path
import argparse,json,os,subprocess,sys,tempfile
HERE=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-software',action='store_true',help='explicit Mesa software test; never hardware performance proof')
    args=parser.parse_args()
    for name in ('input','borders'):
        subprocess.run([str(HERE.parent/'build/graphics'/f'test-desktop-{name}')],check=True,timeout=30)
    with tempfile.TemporaryDirectory(prefix='pocket-graphics-check-') as folder:
        folder=Path(folder);actions=folder/'actions.json';report=folder/'report.json';output=folder/'frame.rgb565'
        actions.write_text(json.dumps([{'menu':True},{'key':'\u001b'},{'launch':'window:Messages'},{'launch':'window:Settings'},{'launch':'terminal:new'},{'app':'surface-room'},{'resize':[123,47]},{'resize':[80,25]}]))
        command=[sys.executable,str(HERE/'run.py'),'--headless','--seconds','4','--state',str(folder/'state'),'--actions',str(actions),'--output',str(output),'--report',str(report),'--effect-backend','cpu','--no-save','--no-animation']
        if args.allow_software:command.append('--allow-software')
        env=dict(os.environ,HOME=str(folder),XDG_STATE_HOME=str(folder/'state'),XDG_CACHE_HOME=str(folder/'cache'),XDG_CONFIG_HOME=str(folder/'config'))
        result=subprocess.run(command,capture_output=True,timeout=45,env=env)
        if result.returncode:raise RuntimeError(result.stderr.decode()+result.stdout.decode())
        data=json.loads(report.read_text())
        if len(data['apps'])<24 or not data['native'] or data['desktop_ansi'] or data['desktop_pty']:raise AssertionError('Desktop registry/pixel contract failed')
        if not any(row['menu'] for row in data['history']):raise AssertionError('Menu was not opened')
        for name in ('Connections','Messages','Settings','Terminal','Surface room'):
            if not any(row['focus']==name for row in data['history']):raise AssertionError('App did not activate: '+name)
        if any(row['errors'] for row in data['history']):raise AssertionError('App construction failed')
        if data['desktop_cells']!=[80,25] or output.stat().st_size!=80*8*25*16*2:raise AssertionError('Resize/output dimensions differ')
        room=data['pixel_apps']['Surface room']
        if room['frames']<=0 or room['cell_layer']:raise AssertionError('Room did not produce direct native pixels')
        if '\x1b[' in result.stdout.decode():raise AssertionError('Desktop emitted terminal escape sequences')
        print(json.dumps(dict(result='passed',renderer=data['renderer'],software_allowed=args.allow_software,apps=len(data['apps']),frames=data['frames'],resize=[123,47,80,25],direct_room_frames=room['frames']),indent=2))
if __name__=='__main__':main()
