import importlib.util,json,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'shell/owner-service'))
import uvpro_tune

class Tests(unittest.TestCase):
    def test_payload_and_band_rejection(self):
        row=dict(rx_mhz=443.3,tx_mhz=448.3,tx_ctcss=103.5,rx_ctcss=None,modes=['FM narrow'])
        raw=uvpro_tune.payload(row);uvpro_tune.validate(raw)
        self.assertEqual(int.from_bytes(raw[:4],'big'),443300000)
        self.assertEqual(int.from_bytes(raw[10:12],'big'),10350)
        with self.assertRaises(ValueError):uvpro_tune.payload(dict(row,rx_mhz=224.18))
        with self.assertRaises(ValueError):uvpro_tune.payload(dict(row,rx_mhz=915))
        self.assertEqual(uvpro_tune.payload({'restore':True}),bytes(16))
    def test_secondary_preserves_aprs_and_verifies_reads(self):
        import shutil
        layout=json.loads((ROOT/'tests/fixtures/uvpro-control-layouts.json').read_text())
        def packed(kind,**values):
            value=0;total=0
            for key,width,field_kind in layout[kind]:
                item=values.get(key,0)
                if field_kind=='str':item=int.from_bytes(str(item).encode().ljust(width//8,b'\0'),'big') if item else 0
                value=(value<<width)|int(item);total+=width
            return value.to_bytes(total//8,'big')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('n810-radio-bandwidth.py','uvpro_tune.py','uvpro_secondary.py'):
                shutil.copy(ROOT/'shell/owner-service'/name,root/name)
            (root/'radio-read-layouts.json').write_text(json.dumps(layout))
            spec=importlib.util.spec_from_file_location('bandwidth',root/'n810-radio-bandwidth.py')
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            request=root/'request';result=root/'result';sent=[]
            tx=mod.Transaction(lambda *args:sent.append(args),request,result)
            row=dict(call='W7DK',rx_mhz=146.8,tx_mhz=146.2,modes=['FM wide'])
            mod.atomic(request,dict(id='test',action='tune_repeater',created_at=time.time(),repeater=row))
            tx.tick(0);tx.tick(2)
            settings=packed('Settings',channel_a_lower=0,channel_b_lower=1,auto_share_loc_ch=1,kiss_en=True)
            beacon=bytes(50)
            memories={0:packed('RfCh',channel_id=0,rx_freq=144390000,tx_freq=144390000),1:packed('RfCh',channel_id=1)}
            responses={20:packed('StatusExt',is_power_on=True),10:settings,33:beacon,4:packed('DevInfo',channel_count=2)}
            handled=0
            while tx.active:
                self.assertLess(handled,20)
                command,data,_=sent[handled];handled+=1
                if command==13:body=memories[data[0]]
                elif command==14:memories[data[0]]=data;body=data[:1]
                elif command==11:responses[10]=data;body=b''
                else:body=responses[command]
                tx.consume(command|0x8000,b'\0'+body)
            self.assertEqual(tx.result['state'],'secondary_tuned')
            self.assertTrue(tx.result['readback_verified'])
            self.assertEqual(memories[0],packed('RfCh',channel_id=0,rx_freq=144390000,tx_freq=144390000))
            self.assertNotIn(35,[item[0] for item in sent])
            self.assertEqual(mod.bits(memories[1],42,30),146800000)
            self.assertEqual(memories[1][15:25],b'W7DK'+bytes(6))
            secondary=tx.secondary
            self.assertEqual(secondary.protected(responses[10],layout['Settings']),(0,0))
            # Explicit restore returns the original B selection and empty slot.
            original_settings=settings
            mod.atomic(request,dict(id='restore',action='tune_repeater',created_at=time.time(),repeater={'restore':True}))
            tx.tick(10);tx.tick(12)
            while tx.active:
                command,data,_=sent[handled];handled+=1
                if command==13:body=memories[data[0]]
                elif command==14:memories[data[0]]=data;body=data[:1]
                elif command==11:responses[10]=data;body=b''
                else:body=responses[command]
                tx.consume(command|0x8000,b'\0'+body)
            self.assertEqual(tx.result['state'],'secondary_restored')
            self.assertEqual(responses[10],original_settings)
            self.assertEqual(mod.bits(memories[1],42,30),0)
