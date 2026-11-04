"""Native BSS capture model: exact received bytes, no RF or transport I/O."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('bss_model_test',ROOT/'n810-messages-model.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
PING=bytes.fromhex('000106204e30414e540121052450494e47')
RECORD=dict(frame=PING.hex(),time='2026-10-17T19:45:40.092Z',direction='radio_to_host')
def field(kind,value):
    value=value.encode() if isinstance(value,str) else value
    return bytes([len(value)+1,kind])+value

class BSSTests(unittest.TestCase):
    def test_exact_ping_missing_id_and_empty_destination(self):
        row=m.parse_receive(RECORD)
        self.assertEqual((row['protocol'],row['source'],row['to'],row['text'],row['id']),('bss','N0ANT','','PING',None))
        self.assertEqual(row['time'],RECORD['time']);self.assertEqual(row['direction'],RECORD['direction'])
        self.assertEqual(row['raw_hex'],RECORD['frame']);self.assertEqual(row['capture'],RECORD)
        self.assertNotIn('capture_id',row);self.assertNotIn('route',row)

    def test_missing_destination_and_counter_zero_differ_from_empty(self):
        frame=b'\0\1'+field(0x20,'N0ANT-7')+b'\x85\0\0'+field(0x24,'café')
        row=m.parse_bss(frame)
        self.assertEqual(row['source'],'N0ANT-7');self.assertIsNone(row['to'])
        self.assertEqual(row['id'],0);self.assertEqual(row['text'],'café')
        self.assertEqual(row['fields'][1],dict(type='counter',value_hex='0000'))

    def test_unknown_fields_and_vendor_capture_provenance_survive(self):
        record=dict(RECORD,frame=(PING+field(0x66,b'\xff\x00')).hex(),origin='vendor_reassembled',wire_frames=['ff0100'])
        row=m.parse_receive(record)
        self.assertEqual(row['fields'][-1],dict(type=0x66,value_hex='ff00'))
        self.assertEqual(row['capture'],record)
        row['capture']['wire_frames'].append('changed')
        self.assertEqual(record['wire_frames'],['ff0100'])

    def test_malformed_bounds_utf8_and_duplicate_identity_are_rejected(self):
        bad=[b'',b'\0',b'\0\1\0',b'\0\1\x05\x24A',b'\0\1\x85',b'\0\1\x85\0',
             b'\0\1'+field(0x24,b'\xff'),b'\0\1'+field(0x20,'ONE')+field(0x20,'TWO'),
             b'\0\1'+b'\x85\0\1'*2,b'\0\1'+field(0x66,b'')*257,b'\0\1'+b'X'*65535]
        for frame in bad:
            with self.subTest(frame=frame[:20]),self.assertRaises(ValueError):m.parse_bss(frame)
        for record in (None,{},dict(RECORD,frame='GG'),dict(RECORD,time={}),dict(RECORD,direction=[])):
            with self.assertRaises(ValueError):m.parse_receive(record)

    def test_protocol_classification_does_not_call_all_ax25_aprs(self):
        ax25=m.kiss_frame('N0ANT',[],'W7DK','hello','A12')[1:-1].replace(b'\xdb\xdc',b'\xc0').replace(b'\xdb\xdd',b'\xdb')
        self.assertEqual(m.classify_frame(ax25),'ax25')
        self.assertEqual(m.parse_receive(dict(RECORD,frame=ax25.hex()))['protocol'],'ax25')
        self.assertEqual(m.classify_frame(PING),'bss')
        self.assertEqual(m.classify_frame(b'\x01\x01'),'kiss_control')
        self.assertEqual(m.classify_frame(b'\0garbage'),'unknown')

    def test_mixed_ingestion_keeps_protocol_and_ack_domains_separate(self):
        state=m.State('N0ANT');pending=state.draft('W7DK','hello',identifier='A12')
        state.begin_submission(pending,[]);state.submitted(pending)
        frame=b'\0\1'+field(0x20,'W7DK')+field(0x21,'N0ANT')+field(0x24,'ackA12')
        row=state.add_record(dict(RECORD,frame=frame.hex()))
        self.assertEqual(row['protocol'],'bss');self.assertEqual(pending['status'],'Submitted')
        self.assertIsNone(state.add_record(dict(RECORD,frame=frame.hex())))
        self.assertIsNone(state.add_record(dict(RECORD,frame=frame.hex(),direction='host_to_radio_written')))
        self.assertEqual(len(state.thread('W7DK')['received']),0)
        self.assertEqual(len(state.thread('W7DK',protocol='bss')['received']),1)
        with self.assertRaises(ValueError):state.begin_submission(row,[])
        state.add('12:45:41 W7DK>APRS ctl=03 pid=f0 :N0ANT    :ackA12')
        self.assertEqual(pending['status'],'Acknowledged')
        self.assertEqual(len(state.received),2)

    def test_repeated_receptions_with_different_times_and_unknown_time(self):
        state=m.State('N0ANT')
        state.add_record(RECORD)
        state.add_record(dict(RECORD,time='2026-10-17T19:45:41.092Z'))
        state.add_record(dict(RECORD,time=None));state.add_record(dict(RECORD,time=None))
        self.assertEqual(len(state.received),4)
        self.assertIsNone(state.received[0]['time'])
        lines=m.detail_lines(state.received[0])
        self.assertIn('BSS RECEIVE DETAILS',lines)
        self.assertTrue(any('Raw KISS hex: '+PING.hex()==line for line in lines))

if __name__=='__main__':unittest.main()
