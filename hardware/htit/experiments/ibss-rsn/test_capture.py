import unittest
import zlib
import struct
import hashlib
import json
from pathlib import Path
import tempfile
from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from verify_capture import verify_frames,MARKER
from capture_probe import tx_metadata
from capture_results import verify_ack_records

KEY=bytes(range(16)) # Public test data, never a device/trial credential.


def sample(number,fcs=True,tail=b'\0'*27):
    header=bytes.fromhex('084000000002eec0ffee020000000001024e383130020000')
    pn=number.to_bytes(6,'little')
    ccmp=pn[:2]+b'\0\x20'+pn[2:]
    aad=b'\x08\x40'+header[4:22]+b'\0\0'
    plain=bytes.fromhex('aaaa0300000088b5')+MARKER+bytes([number-1])+tail
    assert len(plain)==64
    frame=header+ccmp+AESCCM(KEY,tag_length=8).encrypt(b'\0'+header[10:16]+pn[::-1],plain,aad)
    if fcs:frame+=zlib.crc32(frame).to_bytes(4,'little')
    return 'FRAME '+frame.hex()


class CaptureTests(unittest.TestCase):
    def test_ack_status_requires_every_injected_packet_and_success(self):
        frames=[bytes.fromhex(sample(i,False).split()[1]) for i in range(1,17)]
        packets=list(frames)+[frames[0]]
        forged=bytearray(frames[8]);forged[31]^=0x40;packets.append(bytes(forged))
        for frame in frames:
            bad=bytearray(frame);bad[-1]^=1;packets.append(bytes(bad))
        records=[dict(hash=hashlib.sha256(p[24:104]).hexdigest(),flags=0,data_retries=0) for p in packets]
        def lines(values):return ['TX_STATUS '+json.dumps(v) for v in values]
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'replies.txt';path.write_text('\n'.join(p.hex() for p in frames))
            good=verify_ack_records(lines(records),path,True)
            self.assertTrue(good['verified']);self.assertEqual(good['reported'],34)
            self.assertFalse(verify_ack_records(lines(records[:-1]),path,True)['verified'])
            self.assertFalse(verify_ack_records(lines(records+[records[0]]),path,True)['verified'])
            for flags in (1,8):
                changed=[dict(v) for v in records];changed[0]['flags']=flags
                self.assertFalse(verify_ack_records(lines(changed),path,True)['verified'])
            changed=[dict(v) for v in records];changed[0]['hash']='wrong'
            self.assertFalse(verify_ack_records(lines(changed),path,True)['verified'])
    def test_tx_status_flags_retries_and_alignment(self):
        for flags in (0,1,8,0x20):
            packet=struct.pack('<BBHIHB',0,0,11,(1<<15)|(1<<17),flags,7)
            self.assertEqual(tx_metadata(packet),dict(flags=flags,data_retries=7))
        packet=bytearray(21);struct.pack_into('<BBHI',packet,0,0,0,21,(1<<0)|(1<<1)|(1<<15)|(1<<17))
        struct.pack_into('<H',packet,18,1);packet[20]=6
        self.assertEqual(tx_metadata(packet),dict(flags=1,data_retries=6))
        for length in range(21):self.assertIsNone(tx_metadata(packet[:length]))
    def test_tx_status_extended_bitmap_and_missing_status(self):
        packet=bytearray(27);struct.pack_into('<BBHII',packet,0,0,0,27,(1<<31)|(1<<0)|(1<<15)|(1<<17),0)
        struct.pack_into('<H',packet,24,8);packet[26]=3
        self.assertEqual(tx_metadata(packet),dict(flags=8,data_retries=3))
        self.assertIsNone(tx_metadata(bytes.fromhex('0000080000000000')))
        self.assertIsNone(tx_metadata(bytes.fromhex('0000080000000080')))
    def test_complete_trial_with_and_without_fcs(self):
        for fcs in (True,False):
            result=verify_frames([sample(i,fcs) for i in range(1,17)],KEY)
            self.assertTrue(result['pass']);self.assertEqual(result['authenticated_unique_frames'],16)

    def test_partial_trial_is_not_a_pass(self):
        self.assertFalse(verify_frames([sample(1)],KEY)['pass'])

    def test_retransmissions_do_not_count_as_new_packets(self):
        result=verify_frames([sample(1)]*16,KEY)
        self.assertFalse(result['pass']);self.assertEqual(result['duplicate_frames'],15)

    def test_wrong_key_tampering_and_bad_fcs_are_rejected(self):
        self.assertEqual(verify_frames([sample(1)],bytes(reversed(KEY)))['invalid_frames'],1)
        for offset in (4,26,32,40,103,107):
            frame=bytearray.fromhex(sample(1).split()[1]);frame[offset]^=1
            self.assertEqual(verify_frames(['FRAME '+frame.hex()],KEY)['invalid_frames'],1)

    def test_key_holder_nonce_reuse_is_reported(self):
        result=verify_frames([sample(1),sample(1,tail=b'x'*27)],KEY)
        self.assertEqual(result['invalid_frames'],1)

    def test_malformed_capture_and_wrong_key_size_are_rejected(self):
        self.assertEqual(verify_frames(['FRAME not-hex','FRAME 00'],KEY)['invalid_frames'],2)
        with self.assertRaises(ValueError):verify_frames([],b'short')
