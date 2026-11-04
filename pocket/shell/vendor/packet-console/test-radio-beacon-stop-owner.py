import collections
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parent


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


class Tests(unittest.TestCase):
    def test_existing_owner_bridge_allows_only_clear_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('n810-kiss-bridge.py','n810-radio-live.py','uvpro-aprs-listen.py','n810-radio-bandwidth.py','test-radio-bandwidth.py'):
                shutil.copy2(ROOT/name,root/name)
            shutil.copy2(ROOT/'radio-read-layouts.json',root/'radio-read-layouts.json')
            subprocess.run(['patch','--batch','-p1','-i',str(ROOT/'radio-bandwidth-owner.patch')],cwd=root,check=True,stdout=subprocess.DEVNULL)
            text=(ROOT/'radio-beacon-stop-owner.patch').read_text();bridge=text[text.index('--- a/n810-kiss-bridge.py'):]
            patch=root/'bridge.patch';patch.write_text(bridge)
            subprocess.run(['patch','--batch','-p1','-i',str(patch)],cwd=root,check=True,stdout=subprocess.DEVNULL)
            b=load(root/'n810-kiss-bridge.py','stop_bridge');f=load(root/'test-radio-bandwidth.py','stop_fixture')
            raw=f.packed('BSSSettings',aprs_callsign='N0CALL',should_share_location=True)
            desired=raw[:1]+bytes([raw[1]&~16])+raw[2:]
            instance=object.__new__(b.Bridge);instance.tx=collections.deque();instance.tx_size=0;instance.writer=None;instance.modify_radio=lambda:None
            instance.bandwidth_request(34,desired,raw)
            self.assertEqual(instance.tx[0][0][6:8],b'\0\x22');self.assertEqual(instance.tx[0][0][8:],desired)
            instance.tx.clear();instance.tx_size=0
            with self.assertRaises(ValueError):instance.bandwidth_request(34,raw,desired)
            altered=desired[:-1]+bytes([desired[-1]^1])
            with self.assertRaises(ValueError):instance.bandwidth_request(34,altered,raw)
            instance.writer=object()
            with self.assertRaises(RuntimeError):instance.bandwidth_request(34,desired,raw)


if __name__=='__main__':unittest.main()
