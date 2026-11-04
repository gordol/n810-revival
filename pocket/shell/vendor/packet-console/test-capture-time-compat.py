"""Full capture timestamps distinguish days while legacy streams remain valid."""
import importlib.util
from pathlib import Path
import unittest


def load(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


STAMPS=('2026-10-17T12:34:56+00:00','2026-10-18T12:34:56+00:00',
        '2026-10-18T12:34:56.1234567-07:00','2026-10-18 12:34:56+05:30:15.25','2026-10-18T12:34:56Z')
PACKET='W1ABC>APRS ctl=03 pid=f0 :N0CALL   :same message{B1'


class CaptureTimeTests(unittest.TestCase):
    def test_messages_keep_capture_dates_precision_offsets_and_replay_identity(self):
        model=load('n810-messages-model');state=model.State('N0CALL')
        for stamp in STAMPS:
            state.add(stamp+' '+PACKET);state.add(stamp+' '+PACKET)
        self.assertEqual(len(state.received),len(STAMPS))
        self.assertEqual(tuple(row['time'] for row in state.received),STAMPS[::-1])
        legacy=model.State('N0CALL');legacy.add('12:34:56 '+PACKET);legacy.add('12:34:56 '+PACKET)
        self.assertEqual(len(legacy.received),1);self.assertEqual(legacy.received[0]['time'],'12:34:56')

    def test_services_keep_distinct_dates_and_legacy_lines(self):
        model=load('n810-services-model');state=model.State('N0CALL')
        for stamp in STAMPS:
            state.add(stamp+' '+PACKET);state.add(stamp+' '+PACKET)
        self.assertEqual(state.total,len(STAMPS));self.assertEqual(len(state.messages),len(STAMPS))
        self.assertEqual(tuple(row['time'] for row in state.messages),STAMPS[::-1])
        legacy=model.State('N0CALL');legacy.add('12:34:56 '+PACKET);legacy.add('12:34:56 '+PACKET)
        self.assertEqual(legacy.total,1)

    def test_net_announcement_identity_includes_date_and_capture_precision(self):
        calendar=load('n810-net-calendar');raw='W1ABC>APRS ctl=03 pid=f0 >Net tonight'
        rows=[calendar.announcement(stamp+' '+raw) for stamp in STAMPS]
        self.assertTrue(all(rows));self.assertEqual(len({row['id'] for row in rows}),len(STAMPS))
        self.assertEqual(tuple(row['packet_time'] for row in rows),STAMPS)
        self.assertEqual(calendar.announcement(STAMPS[0]+' '+raw)['id'],rows[0]['id'])
        self.assertEqual(calendar.announcement('12:34:56 '+raw)['packet_time'],'12:34:56')


if __name__=='__main__':unittest.main()
