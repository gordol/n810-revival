"""UV-Pro free VFO command 35, documented by HTCommander; no PTT/memory writes."""
import math
import struct


def payload(value):
    if value.get('restore') is True:return bytes(16)
    def freq(key):
        mhz=value.get(key)
        if type(mhz) not in (int,float) or not math.isfinite(mhz) or not (136<=mhz<=174 or 400<=mhz<=520):
            raise ValueError('UV-Pro VFO requires VHF 136–174 or UHF 400–520 MHz')
        return round(mhz*1000000)
    if value.get('dcs'):raise ValueError('DCS tuning is not supported by this VFO encoder')
    if not any(mode.startswith('FM ') for mode in value.get('modes',[])):raise ValueError('Choose an analog FM repeater')
    def tone(key):
        value_t=value.get(key)
        if value_t is None:return 0
        if type(value_t) not in (int,float) or not math.isfinite(value_t) or not 60<=value_t<=260:raise ValueError('Invalid CTCSS tone')
        return round(value_t*100)
    return struct.pack('>IIHHHH',freq('rx_mhz'),freq('tx_mhz'),tone('rx_ctcss'),tone('tx_ctcss'),0,25000)


def validate(raw):
    if raw==bytes(16):return
    if len(raw)!=16:raise ValueError('Invalid VFO payload')
    rx,tx,rt,tt,flags,width=struct.unpack('>IIHHHH',raw)
    payload(dict(rx_mhz=rx/1e6,tx_mhz=tx/1e6,rx_ctcss=rt/100 or None,tx_ctcss=tt/100 or None,modes=['FM wide']))
    if flags!=0 or width!=25000:raise ValueError('Invalid ordinary VFO flags')
