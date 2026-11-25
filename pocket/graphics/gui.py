# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build and run the complete graphical Pocket desktop."""
from pathlib import Path
import os,subprocess,sys
here=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(here/'build.py'),'--runtime-only'],check=True)
if os.environ.get('POCKET_TERMUX') == '1' and not {'--headless','--help','-h'}.intersection(sys.argv[1:]):
    from termux_display import ensure_display
    ensure_display()
    if '--mobile-shell' in sys.argv and os.environ.get('PREFIX'):
        sys.path.insert(0,str(here.parent/'shell'))
        from mobile_shell import TouchInput
        control=TouchInput()
        control.apply()
        print(control.message,file=sys.stderr,flush=True)
options=['-X','faulthandler'] if '--mobile-shell' in sys.argv else []
os.execv(sys.executable,[sys.executable,*options,str(here/'run.py'),*sys.argv[1:]])
