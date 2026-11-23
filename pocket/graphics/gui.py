# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build and run the complete graphical Pocket desktop."""
from pathlib import Path
import os,subprocess,sys
here=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(here/'build.py')],check=True)
if os.environ.get('POCKET_TERMUX') == '1' and not {'--headless','--help','-h'}.intersection(sys.argv[1:]):
    from termux_display import ensure_display
    ensure_display()
os.execv(sys.executable,[sys.executable,str(here/'run.py'),*sys.argv[1:]])
