"""Test boot selection using a fake metadata reader and fake mode command."""
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
service = Path(__file__).resolve().parents[1]/'device/n810-boot-mode.init'
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root/'reader').write_text('#!/bin/sh\ncat "$TEST_REASON"\nexit "$TEST_READER_EXIT"\n')
    (root/'mode').write_text('#!/bin/sh\necho "$*" >> "$TEST_ACTIONS"\nexit "$TEST_MODE_EXIT"\n')
    for name in ('reader','mode'): (root/name).chmod(0o755)
    env=dict(os.environ,N810_BOOT_REASON_COMMAND=str(root/'reader'),N810_BOOT_MODE_COMMAND=str(root/'mode'),
             N810_BOOT_MODE_STATE=str(root/'state/reason'),TEST_REASON=str(root/'reason'),TEST_ACTIONS=str(root/'actions'),N810_BOOT_CHARGER_ONLINE=str(root/'online'),N810_BOOT_CHARGER_WAIT='0')
    def check(reason, reader_exit, mode_exit, expected, supply='1', delay=False):
        (root/'online').write_text(supply+'\n')
        if delay:
            def connect():
                time.sleep(.2); (root/'online').write_text('1\n')
            thread=threading.Thread(target=connect); thread.start()
        (root/'reason').write_text(reason+'\n'); (root/'actions').write_text('')
        state=root/'state/reason'; state.unlink(missing_ok=True)
        result=subprocess.run([str(service),'start'],env=dict(env,TEST_READER_EXIT=str(reader_exit),TEST_MODE_EXIT=str(mode_exit),N810_BOOT_CHARGER_WAIT='2' if delay else '0'),capture_output=True,text=True)
        if delay: thread.join()
        expected_exit = mode_exit if reader_exit==0 and reason=='charger' and (supply=='1' or delay) else 0
        assert result.returncode == expected_exit
        assert (root/'actions').read_text().splitlines()==expected
        assert state.exists() == (result.returncode==0)
        if state.exists():
            before=(root/'actions').read_text()
            subprocess.run([str(service),'start'],env=env,check=True)
            assert (root/'actions').read_text()==before
    check('charger',0,0,['charging'])
    for reason in ('pwr_key','sw_rst','32wd_to','por'): check(reason,0,0,[])
    check('',1,0,[]); check('charger',2,0,[])
    check('charger',0,1,['charging'])
    check('charger',0,0,[],supply='0')
    check('charger',0,0,['charging'],supply='0',delay=True)
    print('PASS: charger-only selection, once-per-boot decision, normal reset reasons, absent/malformed metadata, failed mode entry')
