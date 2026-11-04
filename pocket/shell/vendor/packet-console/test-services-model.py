"""Services model facts and bounded state without terminal/transport imports."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('services_model',HERE/'n810-services-model.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def packet(payload,call='TEST',stamp='12:00:00'):
    return stamp+' '+call+'>APRS,W7DK* ctl=03 pid=f0 '+payload

class ServicesTests(unittest.TestCase):
    def test_import_without_terminal_or_transport(self):
        subprocess.run([sys.executable,'-c',"import runpy,sys;runpy.run_path(sys.argv[1]);assert not any(k in sys.modules for k in ('curses','socket','subprocess'))",str(HERE/'n810-services-model.py')],check=True)
    def test_existing_tui_uses_model_entrypoints(self):
        spec=importlib.util.spec_from_file_location('services_tui',HERE/'n810-aprs-services.py')
        ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
        self.assertIs(ui.State,ui.model.State);self.assertIs(ui.details,ui.model.details)
        self.assertIs(ui.fields,ui.model.fields)

    def test_service_hints_are_advertisements_and_duplicates_bounded(self):
        state=m.State('N0CALL-7');line=packet('>BBS 146.820MHz')
        state.add(line);state.add(line)
        self.assertEqual(state.total,1);self.assertEqual(state.rows(0)[0]['frequencies'],['146.820'])
        self.assertIn('BBS mention',state.rows(0)[0]['hints']);self.assertEqual(state.rows(0)[0]['raw'],line)
        for i in range(2100):state.add(packet('>station '+str(i),call='T'+str(i)))
        self.assertLessEqual(len(state.seen),2000);self.assertLessEqual(len(state.stations),256)
    def test_message_ack_and_own_call(self):
        state=m.State('N0CALL-7')
        state.add(packet(':N0CALL-2 :hello{12'))
        row=state.rows(2)[0];self.assertTrue(row['ours']);self.assertEqual(row['id'],'12')
        state.add(packet(':N0CALL   :ack12'))
        self.assertEqual(state.rows(2)[0]['kind'],'ACK')
        self.assertIn('Acknowledgement', '\n'.join(m.details(state.rows(2)[0])))
        for i in range(210):state.add(packet(':N0CALL   :hello'+str(i)))
        self.assertEqual(len(state.messages),200)
    def test_object_lifecycle_and_status(self):
        state=m.State('N0CALL');state.add(packet(';OBJECT   *111111zBBS'))
        self.assertIn('TEST/OBJECT',state.stations)
        state.add(packet(';OBJECT   _111111zBBS'));self.assertNotIn('TEST/OBJECT',state.stations)
        state.add('REPLAY | hardware unavailable');self.assertIn('REPLAY',state.status)
    def test_display_copy_does_not_modify_original(self):
        state=m.State('N0CALL');line=packet('>BBS\\x0d')
        state.add(line);row=state.rows(0)[0];m.details(row);m.fields(row);m.summary(row)
        self.assertEqual(row['raw'],line);self.assertEqual(row['payload'],'>BBS\\x0d')

if __name__=='__main__':unittest.main()
