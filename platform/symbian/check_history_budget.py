#!/usr/bin/env python3
"""Test the actual prepared EKA2L1 cleanup function, without firmware or device IO."""
from pathlib import Path
import argparse,os,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('--upstream',type=Path,required=True);a=p.parse_args()
s=(a.upstream/'src/emu/services/src/window/classes/gstore.cpp').read_text()
start=s.index('    bool gdi_store_command_collection::clean_old_nonredraw_segments(')
end=s.index('    void gdi_store_command_collection::redraw_done()',start)
with tempfile.TemporaryDirectory(prefix='symbian-history-') as d:
 out=Path(d);(out/'history_cleanup.inc').write_text(s[start:end])
 subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-O1','-g','-fsanitize=address,undefined','-I'+str(out),str(Path(__file__).parent/'runtime/history_budget_test.cpp'),'-o',str(out/'test')],check=True)
 subprocess.run([str(out/'test')],check=True)
