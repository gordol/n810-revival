"""RNode's standard KISS command numbers, shared without importing the RNS stack."""
class KISS:
    FEND=0xc0;FESC=0xdb;TFEND=0xdc;TFESC=0xdd
    CMD_DATA=0;CMD_FREQUENCY=1;CMD_BANDWIDTH=2;CMD_TXPOWER=3;CMD_SF=4;CMD_CR=5
    CMD_RADIO_STATE=6;CMD_DETECT=8;CMD_LEAVE=10;CMD_READY=15
    CMD_FW_VERSION=0x50;CMD_PLATFORM=0x48;CMD_MCU=0x49
    DETECT_REQ=0x73;DETECT_RESP=0x46;RADIO_STATE_OFF=0;RADIO_STATE_ON=1
    @staticmethod
    def escape(data):return data.replace(b'\xdb',b'\xdb\xdd').replace(b'\xc0',b'\xdb\xdc')
