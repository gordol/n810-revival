"""Shared local draft APIs work without curses, radio, or network imports."""
import builtins
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class Tests(unittest.TestCase):
    def test_domain_has_no_terminal_or_transport_imports(self):
        original=builtins.__import__
        def safe(name,*args,**kwargs):
            if name.split('.')[0] in ('curses','socket','subprocess','dbus'):
                raise AssertionError('Domain imported '+name)
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=safe):
            bank=load('n810-radio-library');profile=load('n810-radio-profiles')
            self.assertEqual(bank.channel()['tx_enabled'],False)
            self.assertEqual(profile.defaults()['APRS']['digital_channel'],0)

    def test_tui_reuses_function_objects(self):
        bank=load('n810-radio-banks');profile=load('n810-radio-control')
        for name in ('validate','load','save','import_csv','export_csv'):
            self.assertIs(getattr(bank,name),getattr(bank._library,name))
        for name in ('defaults','validate','load','save'):
            self.assertIs(getattr(profile,name),getattr(profile._profiles,name))

    def test_saved_reads_keep_absence_and_stable_identities(self):
        bank=load('n810-radio-library');profiles=load('n810-radio-profiles')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'banks.json';ppath=root/'profiles.json'
            self.assertIsNone(bank.read_saved(path));self.assertIsNone(profiles.read_saved(ppath))
            self.assertEqual(list(root.iterdir()),[])
            data={'version':1,'banks':[]}
            row=bank.import_csv(data,'name,rx_mhz\nTest,146.52\n','User bank')
            import json
            path.write_text(json.dumps(data))
            actual=bank.read_saved(path)
            self.assertEqual(len(actual['banks']),1)
            self.assertEqual(bank.get_channel(actual,row['id'],row['channels'][0]['id'])['name'],'Test')
            with self.assertRaises(ValueError):bank.get_bank(actual,'missing')
            data['banks'].append(row);path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):bank.read_saved(path)
            ppath.write_text(json.dumps({'version':1,'profiles':{'Custom':{'digital_channel':0}}}))
            saved=profiles.read_saved(ppath)
            self.assertEqual(list(saved['profiles']),['Custom'])
            self.assertEqual(profiles.get_profile(saved,'Custom'),{'digital_channel':0})
            with self.assertRaises(ValueError):profiles.get_profile(saved,'missing')

    def test_copy_on_edit_assign_save_reload_and_csv(self):
        import copy
        bank=load('n810-radio-library');profiles=load('n810-radio-profiles')
        data={'version':1,'banks':[bank.core_bank()]};initial=copy.deepcopy(data)
        data=bank.edit(data,'add_bank',name='Source');source=data['banks'][-1]['id']
        data=bank.edit(data,'add_bank',name='Target');target=data['banks'][-1]['id']
        data=bank.edit(data,'add_channel',bank_id=source,changes={'name':'Local','rx_mhz':146.52})
        identity=bank.get_bank(data,source)['channels'][0]['id']
        before=copy.deepcopy(data)
        with self.assertRaises(ValueError):bank.edit(data,'update_channel',bank_id=source,channel_id=identity,changes={'name':'Changed','rx_mhz':'nan'})
        self.assertEqual(data,before)
        data=bank.edit(data,'update_channel',bank_id=source,channel_id=identity,changes={'tx_ctcss':100})
        data=bank.edit(data,'assign_channel',bank_id=source,channel_id=identity,target_bank_id=target,move=True)
        self.assertEqual(bank.get_bank(data,source)['channels'],[])
        self.assertEqual(bank.get_channel(data,target,identity)['tx_ctcss'],100)
        core=data['banks'][0]['channels'][0]['id']
        for operation,params in [('delete_bank',{}),('add_channel',{}),('rename_bank',{'name':'Bad'}),('delete_channel',{'channel_id':core}),('assign_channel',{'channel_id':core,'target_bank_id':target,'move':True})]:
            with self.assertRaises(ValueError):bank.edit(data,operation,bank_id='core',**params)
        copied=bank.edit(data,'assign_channel',bank_id='core',channel_id=core,target_bank_id=target)
        assigned=bank.get_bank(copied,target)['channels'][-1]
        self.assertNotEqual(assigned['id'],core);self.assertNotIn('hardware_slot',assigned)
        copied=bank.edit(copied,'copy_bank',bank_id='core')
        self.assertTrue(all('hardware_slot' not in row for row in copied['banks'][-1]['channels']))
        self.assertEqual(initial['banks'][0],data['banks'][0])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'banks.json';bank.save(path,copied)
            self.assertEqual(bank.read_saved(path),copied)
            csv=bank.export_csv(bank.get_bank(copied,target))
            imported=bank.edit(copied,'import_csv',text=csv,name='Imported')
            self.assertEqual(len(imported['banks'][-1]['channels']),2)
        p=profiles.defaults();updated=profiles.edit_profile(p,'APRS',{'rx_ctcss':100})
        self.assertIsNone(p['APRS']['rx_ctcss']);self.assertEqual(updated['APRS']['rx_ctcss'],100)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'profiles.json';profiles.save(path,updated)
            self.assertEqual(profiles.load(path),updated)
        for changes in ({'digital_channel':1},{'hardware_slot':7}):
            with self.assertRaises(ValueError):profiles.edit_profile(p,'APRS',changes)

    def test_csv_draft_and_file_roundtrip(self):
        bank=load('n810-radio-library');profiles=load('n810-radio-profiles')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data={'version':1,'banks':[]}
            row=bank.import_csv(data,'name,rx_mhz,tx_ctcss\nLocal,146.52,100\n','Test')
            self.assertFalse(row['channels'][0]['tx_enabled'])
            before=len(data['banks'])
            with self.assertRaises(ValueError):bank.import_csv(data,'name,rx_mhz\nBad,nan\n','Bad')
            self.assertEqual(len(data['banks']),before)
            bank.save(root/'banks.json',data)
            self.assertEqual(bank.load(root/'banks.json'),data)
            saved=profiles.defaults();saved['APRS']['rx_ctcss']=100
            profiles.save(root/'profiles.json',saved)
            self.assertEqual(profiles.load(root/'profiles.json'),saved)
            for path in root.iterdir():self.assertEqual(path.stat().st_mode&0o777,0o600)


if __name__=='__main__':unittest.main()
