import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import uvpro_bank


class BankRead(unittest.TestCase):
    def run_radio(self, end_bank=0, selected=None):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            vendor=HERE.parent/'vendor/packet-console'
            for name in ('n810-radio-backup.py','radio-read-layouts.json'):
                shutil.copyfile(vendor/name,root/name)
            layouts=json.loads((root/'radio-read-layouts.json').read_text())
            def frame(name, **fields):
                value=width=0
                for field,bits,_ in layouts[name]:
                    value=(value<<bits)|fields.get(field,0)
                    width+=bits
                return value.to_bytes(width//8,'big')
            from unittest.mock import patch
            with patch.object(uvpro_bank,'__file__',str(root/'uvpro_bank.py')):
                job=uvpro_bank.download(selected,'fixture',root/'saved',lambda p,v:p.write_text(json.dumps(v)))
                request=next(job);sent=[]
                while True:
                    cmd,payload=request
                    if cmd==20:raw=frame('StatusExt',curr_region=end_bank if sent else 0)
                    elif cmd==4:raw=frame('DevInfo',region_count=2,channel_count=3)
                    elif cmd==73:raw=payload+b'Group'+str(payload[0]).encode()
                    elif cmd==13:raw=frame('RfCh',channel_id=payload[0],rx_freq=55000000+payload[0])
                    else:self.fail('Unexpected command '+str(cmd))
                    sent.append((cmd,payload))
                    try:request=job.send(raw)
                    except StopIteration:break
                    except ValueError:
                        self.assertFalse(list(root.glob('saved/*/backup.json')))
                        raise
                result=json.loads(next(root.glob('saved/*/backup.json')).read_text())
                return sent,result

    def test_reads_current_channels_and_all_names(self):
        sent,snapshot=self.run_radio()
        self.assertEqual([cmd for cmd,_ in sent],[20,4,73,73,13,13,13,20])
        self.assertEqual(snapshot['bank_names'],['Group0','Group1'])
        self.assertEqual([r['decoded']['rx_freq'] for r in snapshot['banks'][0]['channels']],
                         [55000000,55000001,55000002])
    def test_changed_bank_discards_download(self):
        with self.assertRaisesRegex(ValueError,'changed'):self.run_radio(end_bank=1)
    def test_selected_inactive_bank(self):
        with self.assertRaisesRegex(ValueError,'active bank only'):self.run_radio(selected=1)
