"""Verify retained TX-status records against expected synthetic frames."""
from collections import Counter
import hashlib,json

def verify_ack_records(lines,reply_file,negative_each):
    frames=[bytes.fromhex(line) for line in reply_file.read_text().splitlines()]
    if len(frames)!=16:return dict(verified=False,reported=0)
    packets=list(frames)+[frames[0]]
    forged=bytearray(frames[8]);forged[31]^=0x40;packets.append(bytes(forged))
    if negative_each:
        for frame in frames:
            bad=bytearray(frame);bad[-1]^=1;packets.append(bytes(bad))
    expected=Counter(hashlib.sha256(p[24:104]).hexdigest() for p in packets)
    try:statuses=[json.loads(s[len('TX_STATUS '):]) for s in lines if s.startswith('TX_STATUS ')]
    except (ValueError,TypeError):return dict(verified=False,reported=0)
    try:
        actual=Counter(s['hash'] for s in statuses)
        failed=sum(bool(s['flags']&1) for s in statuses)
        no_ack=sum(bool(s['flags']&8) for s in statuses)
        retries=[s['data_retries'] for s in statuses if s['data_retries'] is not None]
        return dict(verified=actual==expected and not failed and not no_ack,
                    reported=len(statuses),expected=len(packets),failed=failed,
                    no_ack_requested=no_ack,max_data_retries=max(retries,default=None))
    except (KeyError,TypeError):return dict(verified=False,reported=len(statuses))
