import importlib.util
from pathlib import Path
import json,unittest
spec=importlib.util.spec_from_file_location('backup',Path(__file__).with_name('n810-radio-backup.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
class Tests(unittest.TestCase):
 def test_read_framing_and_write_guard(self):
  self.assertEqual(b.frame(4,b'\3').hex(),'ff0100010002000403')
  link=b.Link(None)
  for cmd in [11,14,30,31,34,35,60,64]:
   with self.assertRaises(ValueError):link.request(cmd)
 def test_channel_decode(self):
  layouts=json.loads(Path(__file__).with_name('radio-read-layouts.json').read_text())
  raw=b'\0'+int(144390000).to_bytes(4,'big')+int(146520000).to_bytes(4,'big')+bytes(6)+b'TEST\0\0\0\0\0\0'
  row=b.decode(raw,layouts['RfCh'])
  self.assertEqual(row['tx_freq'],144390000);self.assertEqual(row['rx_freq'],146520000)
  self.assertEqual(row['name_str'],'TEST');self.assertEqual(row['_decoded_bits'],200)
 def test_sweep_restores_original_bank_settings_and_beacon(self):
  import tempfile
  from unittest.mock import patch,MagicMock
  layouts=json.loads(Path(__file__).with_name('radio-read-layouts.json').read_text())
  def encode(layout,**fields):
   number=size=0
   for name,width,_ in layouts[layout]:
    number=(number<<width)|fields.get(name,0);size+=width
   return number.to_bytes(size//8,'big')
  initial_beacon=encode('BSSSettings',should_share_location=True)
  for interrupt in (False,True):
   with self.subTest(interrupt=interrupt),tempfile.TemporaryDirectory() as tmp:
    state=dict(bank=1,settings=bytes(22),beacon=initial_beacon)
    def request(command,payload=b'',index=None,**kw):
     raw=b''
     if command==4:raw=encode('DevInfo',region_count=3,channel_count=2)
     elif command==20:raw=encode('StatusExt',curr_region=state['bank'])
     elif command==10:raw=state['settings']
     elif command==11:state['settings']=payload
     elif command==33:raw=state['beacon']
     elif command==34:state['beacon']=payload
     elif command==73:raw=payload+b'Bank'
     elif command==13:
      if interrupt and state['bank']==0:raise ConnectionError('test read failure')
      raw=encode('RfCh',channel_id=index)
     elif command==60:
      self.assertFalse(state['beacon'][1]&0x10)
      state.update(bank=payload[0],settings=bytes([1])*22)
     return dict(status=0,reply_hex='00'+raw.hex())
    folder=Path(tmp)/'snapshot';link=MagicMock(trace=[]);link.request.side_effect=request
    with patch('sys.argv',['backup','--all-banks','--pause-beacon','--output',str(folder)]),patch.object(b,'Link',return_value=link),patch.object(b,'socket'),patch.object(b.subprocess,'check_output',return_value='Channel: 1'),patch.object(b.signal,'signal'),patch.object(b.time,'sleep'):
     if interrupt:
      with self.assertRaises(ConnectionError):b.main()
     else:b.main()
    saved=json.loads((folder/'backup.json').read_text())
    self.assertEqual(state,dict(bank=1,settings=bytes(22),beacon=initial_beacon))
    self.assertTrue(saved['beacon_restored'] and saved['restored'])
    self.assertEqual(saved['complete'],not interrupt)
    if not interrupt:self.assertEqual([(v['index'],len(v['channels'])) for v in saved['banks']],[(1,2),(0,2),(2,2)])
if __name__=='__main__':unittest.main()
