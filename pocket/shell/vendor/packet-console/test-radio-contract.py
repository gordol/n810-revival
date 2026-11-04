"""Read-only browser contract checks against radio decoder helpers."""
import importlib.util
from pathlib import Path
import json
import tempfile
import unittest


def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


readback=load('n810-radio-readback')
backup=load('n810-radio-backup')


class Contract(unittest.TestCase):
    def test_frequency_units_and_flags(self):
        fields=dict(channel_id=0,name_str='APRS',rx_freq=144390000,tx_freq=144990000,
                    rx_sub_audio=10000,tx_sub_audio=23,rx_mod=0,tx_mod=1,bandwidth=0,
                    tx_at_max_power=False,tx_at_med_power=True,tx_disable=True,
                    scan=False,mute=False,talk_around=False,pre_de_emph_bypass=True)
        details=dict(readback.channel_details({'index':0,'decoded':fields}))
        self.assertEqual(details['RX'],'144.390000 MHz')
        self.assertEqual(details['Offset'],'+0.600 MHz')
        self.assertEqual(details['RX tone'],'100.0 Hz')
        self.assertEqual(details['TX tone'],'DCS 23')
        self.assertEqual(details['Bandwidth'],'Narrow')
        self.assertEqual(details['Power'],'Medium')
        self.assertEqual(details['Transmit'],'Disabled')

    def test_layout_preserves_raw_hz_and_zero_index(self):
        layouts=json.loads(Path(__file__).with_name('radio-read-layouts.json').read_text())
        values={'channel_id':0,'tx_freq':144390000,'rx_freq':144390000,'name_str':'APRS'}
        bits=0;total=0
        for key,width,kind in layouts['RfCh']:
            value=values.get(key,0)
            if kind=='str':value=int.from_bytes(str(value).encode().ljust(width//8,b'\0'),'big')
            bits=(bits<<width)|value;total+=width
        decoded=backup.decode(bits.to_bytes(total//8,'big'),layouts['RfCh'])
        self.assertEqual(decoded['channel_id'],0)
        self.assertEqual(decoded['rx_freq'],144390000)
        self.assertEqual(decoded['name_str'],'APRS')
        self.assertEqual(decoded['_decoded_bits'],decoded['_available_bits'])

    def test_partial_download_never_replaces_completed(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name,data in [('1',{'complete':True,'banks':[]}),('2',{'complete':True,'restore_bank':{},'restored':False}),('3',{'complete':False})]:
                path=root/name;path.mkdir();(path/'backup.json').write_text(json.dumps(data))
            path,data=readback.latest(root)
            self.assertEqual(path.parent.name,'1')


if __name__=='__main__':unittest.main()
