"""Synthetic Linux snapshots; never queries device hardware or the network."""
import ast
import contextlib
import importlib.util
import io
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

source=Path(__file__).with_name('read-state.py')
functions=[n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ('system_snapshot','local_status')]
exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'))


class Collector(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.proc=self.root/'proc';self.net=self.root/'net'
        self.proc.mkdir();self.net.mkdir()
    def write(self,path,text):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    def test_units_counter_semantics_and_wifi_link_only(self):
        self.write(self.proc/'sys/kernel/random/boot_id','synthetic-boot\n')
        self.write(self.proc/'uptime','120.5 100.0\n')
        self.write(self.proc/'stat','cpu 100 20 30 400 50 10 5 0 99 99\n')
        self.write(self.proc/'loadavg','0.10 0.20 0.30 1/40 100\n')
        self.write(self.proc/'meminfo','MemTotal: 1000 kB\nMemAvailable: 300 kB\nMemFree: 10 kB\nSwapTotal: 200 kB\nSwapFree: 150 kB\n')
        self.write(self.proc/'vmstat','pswpin 12\npswpout 24\n')
        for field,value in [('rx_bytes','1000'),('tx_bytes','2000'),('rx_packets','10'),('tx_packets','20')]:self.write(self.net/'wlan0/statistics'/field,value)
        calls=[]
        def link(args,**kwargs):
            calls.append((args,kwargs));return SimpleNamespace(returncode=0,stdout='Connected to example\n\tsignal: -53 dBm\n')
        result=system_snapshot(self.proc,self.net,link);system=result['system']
        self.assertEqual(system['cpu'],{'total_ticks':615,'idle_ticks':450})
        self.assertEqual(system['memory_bytes']['available'],307200)
        self.assertEqual(system['memory_bytes']['free'],10240)
        self.assertEqual(system['swap']['in_pages'],12)
        self.assertEqual(result['network_stats']['wlan0']['rx_bytes'],1000)
        self.assertEqual(result['wifi']['wlan0']['signal_dbm'],-53)
        self.assertEqual(calls[0][0][-3:],['dev','wlan0','link']);self.assertEqual(calls[0][1]['timeout'],1)
    def test_missing_counters_remain_unknown(self):
        result=system_snapshot(self.proc,self.net)
        self.assertIsNone(result['system']['cpu']);self.assertIsNone(result['system']['memory_bytes']['available'])
        self.assertIsNone(result['system']['boot_id']);self.assertEqual(result['network_stats'],{})
    def test_link_timeout_and_disconnection_do_not_invent_signal(self):
        (self.net/'wlan0').mkdir()
        def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('iw',1)
        self.assertIsNone(system_snapshot(self.proc,self.net,timeout)['wifi']['wlan0']['signal_dbm'])
        result=system_snapshot(self.proc,self.net,lambda *a,**k:SimpleNamespace(returncode=0,stdout='Not connected.\n'))
        self.assertEqual(result['wifi']['wlan0']['state'],'disconnected')
        self.assertIsNone(result['wifi']['wlan0']['signal_dbm'])
    def test_kernel_signal_and_carrier_avoid_helper_and_clear_on_disconnect(self):
        self.write(self.proc/'net/wireless','wlan0: 0000 69. -41. -256 0 0 0\n')
        self.write(self.net/'wlan0/carrier','1\n')
        helper=lambda *a,**k:self.fail('Kernel observation must not spawn iw')
        result=system_snapshot(self.proc,self.net,helper)['wifi']['wlan0']
        self.assertEqual(result['state'],'connected');self.assertEqual(result['signal_dbm'],-41)
        self.assertIsNotNone(result['observed_at'])
        self.write(self.net/'wlan0/carrier','0\n')
        result=system_snapshot(self.proc,self.net,helper)['wifi']['wlan0']
        self.assertEqual(result['state'],'disconnected');self.assertIsNone(result['signal_dbm'])
        self.write(self.net/'wlan0/carrier','1\n')
        self.assertEqual(system_snapshot(self.proc,self.net,helper)['wifi']['wlan0']['signal_dbm'],-41)

    def test_unsupported_or_malformed_signal_uses_original_link_query(self):
        self.write(self.net/'wlan0/carrier','1\n')
        calls=[]
        def link(*args,**kwargs):calls.append(True);return SimpleNamespace(returncode=0,stdout='Not connected.\n')
        for signal in ('0','69','nan','inf','-256','broken'):
            self.write(self.proc/'net/wireless','wlan0: 0000 69. '+signal+' 0\n')
            observation=system_snapshot(self.proc,self.net,link)['wifi']['wlan0']
            self.assertEqual(observation['state'],'disconnected');self.assertIsNone(observation['signal_dbm'])
        self.assertEqual(len(calls),6)

    def test_carrier_drop_during_signal_read_does_not_publish_stale_rssi(self):
        self.write(self.proc/'net/wireless','wlan0: 0000 69. -41. 0\n')
        self.write(self.net/'wlan0/carrier','1\n')
        original=Path.open
        def opened(path,*args,**kwargs):
            if path==self.proc/'net/wireless':self.write(self.net/'wlan0/carrier','0\n')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',opened):
            observation=system_snapshot(self.proc,self.net,lambda *a,**k:self.fail('No helper needed'))['wifi']['wlan0']
        self.assertEqual(observation['state'],'disconnected');self.assertIsNone(observation['signal_dbm'])

    def test_local_status_reuses_existing_power_and_interface_shapes(self):
        power=self.root/'power'
        self.write(power/'battery/uevent','POWER_SUPPLY_TYPE=Battery\nPOWER_SUPPLY_CAPACITY=89\n')
        self.write(self.net/'usb0/operstate','down\n')
        result=local_status(self.proc,self.net,power)
        self.assertEqual(result['power'],[{'POWER_SUPPLY_TYPE':'Battery','POWER_SUPPLY_CAPACITY':'89'}])
        self.assertEqual(result['network'],{'usb0':'down'})
    def test_import_does_not_collect_or_connect(self):
        spec=importlib.util.spec_from_file_location('safe_status_collector',source)
        module=importlib.util.module_from_spec(spec);output=io.StringIO()
        with patch.object(socket,'socket',side_effect=AssertionError('no socket on import')),patch.object(Path,'open',side_effect=AssertionError('no data read on import')),contextlib.redirect_stdout(output):
            spec.loader.exec_module(module)
        self.assertEqual(output.getvalue(),'')
        self.assertTrue(callable(module.local_status))


if __name__=='__main__':unittest.main()
