#!/usr/bin/env python3
"""Offline calendar, DST, reminder and APRS-announcement checks."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('calendar',Path(__file__).with_name('n810-net-calendar.py'))
cal=importlib.util.module_from_spec(spec);spec.loader.exec_module(cal)

class CalendarTests(unittest.TestCase):
    def data(self,**changes):
        row=dict(id='net',name='Test net',call='TEST',frequency_mhz=146.82,weekdays=list(range(7)),time='19:30',timezone='America/Los_Angeles',source_url='https://example.org/net',checked='2026-10-15')
        row.update(changes);return dict(version=1,nets=[row])
    def test_local_evening_survives_fall_transition(self):
        rows=cal.upcoming(self.data(),dt.datetime(2026,10,30,tzinfo=cal.UTC),days=5)
        self.assertTrue(all(row['local'].hour==19 for row in rows))
        self.assertEqual({row['start'].hour for row in rows},{2,3})
    def test_local_evening_survives_spring_transition(self):
        rows=cal.upcoming(self.data(),dt.datetime(2026,3,6,tzinfo=cal.UTC),days=5)
        self.assertEqual({row['start'].hour for row in rows},{2,3})
        self.assertTrue(all(row['local'].hour==19 for row in rows))
    def test_weekday_in_schedule_zone_not_utc(self):
        rows=cal.upcoming(self.data(weekdays=[3]),dt.datetime(2026,10,15,6,tzinfo=cal.UTC))
        self.assertEqual(rows[0]['local'].weekday(),3)
        self.assertEqual(rows[0]['start'].weekday(),4)
    def test_utc_schedule_stays_utc(self):
        rows=cal.upcoming(self.data(timezone='UTC'),dt.datetime(2026,10,30,tzinfo=cal.UTC),days=5)
        self.assertTrue(all(row['start'].hour==19 for row in rows))
    def test_gap_and_fold_need_resolution(self):
        z=cal.ZoneInfo('America/Los_Angeles')
        self.assertEqual(cal.wall_times(dt.date(2026,3,8),'02:30',z),[])
        self.assertEqual(len(cal.wall_times(dt.date(2026,11,1),'01:30',z)),2)
    def test_reminders_are_bounded_and_deduplicated(self):
        now=dt.datetime(2026,10,16,2,20,tzinfo=cal.UTC)
        rows=cal.upcoming(self.data(),now)
        self.assertEqual(len(cal.due(rows,now,15,{})),1)
        self.assertEqual(cal.due(rows,now,0,{}),[])
        self.assertEqual(cal.due(rows,now,15,{rows[0]['occurrence']:None}),[])
    def test_unknown_announcements_do_not_become_schedules(self):
        row=cal.announcement('12:00:00 CLUB>APRS ctl=03 pid=f0 >Net Tu9PM 146.820MHz')
        self.assertEqual(row['kind'],'Net mention')
        self.assertNotIn('start',row)
        self.assertIsNone(cal.announcement('12:00:00 CLUB>APRS ctl=03 pid=f0 >hello'))
        self.assertEqual(cal.announcement('12:00:00 CLUB>APRS ctl=03 pid=f0 :BLN1     :Net starts soon')['kind'],'Bulletin')
    def test_pack_import_and_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'nets.json';cal.atomic(path,self.data())
            self.assertEqual(cal.load(path)['nets'][0]['timezone'],'America/Los_Angeles')
            data=self.data();data['nets'].append(data['nets'][0]);cal.atomic(path,data)
            with self.assertRaises(ValueError):cal.load(path)
    def test_ics_exports_exact_utc_instants(self):
        rows=cal.upcoming(self.data(),dt.datetime(2026,10,30,tzinfo=cal.UTC),days=5)
        text=cal.ical(rows)
        self.assertEqual(text.count('BEGIN:VEVENT'),len(rows))
        self.assertIn('DTSTART:20261030T023000Z',text)
        self.assertIn('DTSTART:20261102T033000Z',text)
        self.assertTrue(all(len(line.encode())<=75 for line in text.split('\r\n')))

if __name__=='__main__':unittest.main()
