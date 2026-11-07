import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('messages',Path(__file__).with_name('n810-messages-model.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Conversations(unittest.TestCase):
    def test_mine_bidirectional_and_exact_ssid(self):
        rows=[dict(source='W7DK',to='N0DEM',text='in'),dict(source='N0DEM',to='W7DK',text='echo'),dict(source='W7DK',to='N0DEM-7',text='other')]
        groups=m.conversation_groups('N0DEM',rows,[dict(to='W7DK',text='draft',status='Draft')])
        self.assertEqual(len(groups),1);self.assertEqual(groups[0]['endpoints'],('N0DEM','W7DK'))
        self.assertEqual(len(groups[0]['received']),2);self.assertEqual(len(groups[0]['outbox']),1)
        self.assertEqual(groups[0]['counts'],dict(received=2,outbox=1,drafts=1))
        groups[0]['received'][0]['text']='changed';self.assertEqual(rows[0]['text'],'in')
    def test_observed_pairs_and_native_identity(self):
        rows=[dict(source='W7DK',to='ONE'),dict(source='W7DK',to='TWO'),dict(protocol='bss',source='W7DK',to=''),dict(protocol='bss',source='W7DK',to=None)]
        self.assertEqual(m.conversation_groups('N0DEM',rows),[])
        self.assertEqual(len(m.conversation_groups('N0DEM',rows,traffic='all')),4)
    def test_unknown_sources_not_one_person(self):
        rows=[dict(protocol='bss',source=None,to='N0DEM',text=str(i)) for i in range(2)]
        self.assertEqual(len(m.conversation_groups('N0DEM',rows)),2)
    def test_bounds_and_invalid_filter(self):
        self.assertEqual(len(m.conversation_groups('N0DEM',[dict(source=str(i),to='N0DEM') for i in range(300)])),200)
        with self.assertRaises(ValueError):m.conversation_groups('N0DEM',traffic='heard')

class Diagnostics(unittest.TestCase):
    def test_bss_failure_preserves_capture(self):
        record=dict(frame='0001052441',wire_frames=['abc'],time='original')
        result=m.receive_diagnostic(record)
        self.assertEqual(result['protocol'],'bss');self.assertEqual(result['stages'][-1]['stage'],'native_bss')
        self.assertIn('Truncated',result['stages'][-1]['reason']);self.assertEqual(result['capture'],record)
        result['capture']['wire_frames'].append('changed');self.assertEqual(record['wire_frames'],['abc'])
    def test_command_port_unknown_and_bad_hex(self):
        for frame,stage,status in [('01','kiss','unsupported'),('1001','discriminator','unsupported'),('0067617262616765','discriminator','unsupported'),('GG','capture_hex','invalid')]:
            with self.subTest(frame=frame):
                result=m.receive_diagnostic(dict(frame=frame));self.assertEqual((result['stages'][-1]['stage'],result['stages'][-1]['status']),(stage,status))
    def test_bss_empty_destination_is_not_invented(self):
        result=m.receive_diagnostic(dict(frame='000106204e3044454d0121052450494e47'))
        self.assertEqual(result['observation']['to'],'');self.assertEqual(result['stages'][-1]['status'],'recognized')
    def test_ax25_does_not_claim_aprs(self):
        frame=b'\0'+m.address('APRS')+m.address('N0DEM',True)+b'\x03\xf0not a message'
        result=m.receive_diagnostic(dict(frame=frame.hex()))
        self.assertEqual(result['protocol'],'ax25');self.assertIsNone(result['observation'])
        self.assertEqual(result['stages'][-1],dict(stage='aprs',status='not_tried',reason='No APRS payload decoder invoked'))

if __name__=='__main__':unittest.main()
