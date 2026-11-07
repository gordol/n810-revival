#!/usr/bin/env python3
"""Open shared radio UI windows without opening another Bluetooth connection."""
import os,subprocess,sys,shlex
from pathlib import Path

def open_window(name):
    desktop=os.environ.get('N810_DESKTOP_SOCKET')
    if desktop:
        try:
            sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
            from desktop_command import exchange
            result=exchange(desktop,{'activate':name},timeout=1)
            if not result.get('ok'):raise RuntimeError(result.get('error','Cannot open desktop window'))
            return
        except (OSError,ValueError) as error:raise RuntimeError('Desktop activation unavailable: '+str(error)) from error
    aliases={'Repeaters':'Radio Services','Radio Directory':'Radio Services','Services Directory':'Radio Services','Directory':'Stations','Heard Stations':'Stations'}
    name=aliases.get(name,name)
    pane=os.environ.get('TMUX_PANE')
    if not pane:raise RuntimeError('Open this from the shared tmux session')
    session=subprocess.check_output(['n810-tmux','display-message','-p','-t',pane,'#{session_name}'],text=True).strip()
    commands={'Nets':['python3','/home/nokia/n810-nets.py'],
              'Radio Services':['python3','/home/nokia/n810-repeaters.py'],
              'Radio':['python3','/home/nokia/n810-radio-control.py'],
              'Radio Preview':['python3','/home/nokia/n810-radio-preview.py'],
              'Stations':['python3','/home/nokia/n810-aprs-directory.py'],
              'Messages':['python3','/home/nokia/n810-aprs-messages.py','--call','N0DEM'],
              'APRS':['python3','/home/nokia/n810-aprs-view.py','--socket','/dev/shm/n810-aprs.sock']}
    windows=subprocess.check_output(['n810-tmux','list-windows','-t',session,'-F','#{window_id}\t#{window_name}'],text=True)
    for row in windows.splitlines():
        identity,title=row.split('\t',1)
        if aliases.get(title,title)==name:
            if title!=name:subprocess.run(['n810-tmux','rename-window','-t',identity,name],check=True)
            panes=subprocess.check_output(['n810-tmux','list-panes','-t',identity,'-F','#{pane_id}\t#{pane_current_command}'],text=True).splitlines()
            if len(panes)==1:
                pane_id,command=panes[0].split('\t',1)
                if command in ('bash','sh','zsh','dash'):
                    subprocess.run(['n810-tmux','send-keys','-t',pane_id,'C-u',shlex.join(commands[name]),'Enter'],check=True)
            subprocess.run(['n810-tmux','select-window','-t',identity],check=True);return
    subprocess.run(['n810-tmux','new-window','-t',session,'-n',name,*commands[name]],check=True)

if __name__=='__main__':open_window(sys.argv[1] if len(sys.argv)>1 else 'Messages')
