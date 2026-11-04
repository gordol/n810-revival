# Reticulum License
#
# Copyright (c) 2016-2026 Mark Qvist
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# - The Software shall not be used in any kind of system which includes amongst
#   its functions the ability to purposefully do harm to human beings.
#
# - The Software shall not be used, directly or indirectly, in the creation of
#   an artificial intelligence, machine learning or language model training
#   dataset, including but not limited to any use that contributes to the
#   training or development of such a model or algorithm.
#
# - The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Derived from the pinned official RNS 1.5.7 readLoop.
# Descriptor readiness drives the generator; lifecycle and retries are external.
import time
import RNS
from RNS.Interfaces.RNodeInterface import KISS, RNodeInterface

class Parser:
    def parser_events(self):
        try:
            in_frame = False
            escape = False
            command = KISS.CMD_UNKNOWN
            data_buffer = b""
            command_buffer = b""
            last_read_ms = int(time.time()*1000)

            while self.serial.is_open:
                if self.serial.in_waiting:
                    byte = ord(self.serial.read(1))
                    last_read_ms = int(time.time()*1000)

                    if (in_frame and byte == KISS.FEND and command == KISS.CMD_DATA):
                        in_frame = False
                        self.process_incoming(data_buffer)
                        data_buffer = b""
                        command_buffer = b""
                    elif (byte == KISS.FEND):
                        in_frame = True
                        command = KISS.CMD_UNKNOWN
                        data_buffer = b""
                        command_buffer = b""
                    elif (in_frame and len(data_buffer) < self.HW_MTU):
                        if (len(data_buffer) == 0 and command == KISS.CMD_UNKNOWN):
                            command = byte
                        elif (command == KISS.CMD_DATA):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                data_buffer = data_buffer+bytes([byte])
                        elif (command == KISS.CMD_FREQUENCY):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 4):
                                    self.r_frequency = command_buffer[0] << 24 | command_buffer[1] << 16 | command_buffer[2] << 8 | command_buffer[3]
                                    RNS.log(str(self)+" Radio reporting frequency is "+str(self.r_frequency/1000000.0)+" MHz", RNS.LOG_DEBUG)
                                    self.updateBitrate()

                        elif (command == KISS.CMD_BANDWIDTH):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 4):
                                    self.r_bandwidth = command_buffer[0] << 24 | command_buffer[1] << 16 | command_buffer[2] << 8 | command_buffer[3]
                                    RNS.log(str(self)+" Radio reporting bandwidth is "+str(self.r_bandwidth/1000.0)+" KHz", RNS.LOG_DEBUG)
                                    self.updateBitrate()

                        elif (command == KISS.CMD_TXPOWER):
                            self.r_txpower = byte
                            RNS.log(str(self)+" Radio reporting TX power is "+str(self.r_txpower)+" dBm", RNS.LOG_DEBUG)
                        elif (command == KISS.CMD_SF):
                            self.r_sf = byte
                            RNS.log(str(self)+" Radio reporting spreading factor is "+str(self.r_sf), RNS.LOG_DEBUG)
                            self.updateBitrate()
                        elif (command == KISS.CMD_CR):
                            self.r_cr = byte
                            RNS.log(str(self)+" Radio reporting coding rate is "+str(self.r_cr), RNS.LOG_DEBUG)
                            self.updateBitrate()
                        elif (command == KISS.CMD_RADIO_STATE):
                            self.r_state = byte
                            if self.r_state:
                                pass
                            else:
                                RNS.log(str(self)+" Radio reporting state is offline", RNS.LOG_DEBUG)

                        elif (command == KISS.CMD_RADIO_LOCK):
                            self.r_lock = byte
                        elif (command == KISS.CMD_FW_VERSION):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 2):
                                    self.maj_version = int(command_buffer[0])
                                    self.min_version = int(command_buffer[1])
                                    self.validate_firmware()

                        elif (command == KISS.CMD_STAT_RX):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 4):
                                    self.r_stat_rx = ord(command_buffer[0]) << 24 | ord(command_buffer[1]) << 16 | ord(command_buffer[2]) << 8 | ord(command_buffer[3])

                        elif (command == KISS.CMD_STAT_TX):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 4):
                                    self.r_stat_tx = ord(command_buffer[0]) << 24 | ord(command_buffer[1]) << 16 | ord(command_buffer[2]) << 8 | ord(command_buffer[3])

                        elif (command == KISS.CMD_STAT_RSSI):
                            self.r_stat_rssi = byte-RNodeInterface.RSSI_OFFSET
                        elif (command == KISS.CMD_STAT_SNR):
                            self.r_stat_snr = int.from_bytes(bytes([byte]), byteorder="big", signed=True) * 0.25
                            try:
                                sfs = self.r_sf-7
                                snr = self.r_stat_snr
                                q_snr_min = RNodeInterface.Q_SNR_MIN_BASE-sfs*RNodeInterface.Q_SNR_STEP
                                q_snr_max = RNodeInterface.Q_SNR_MAX
                                q_snr_span = q_snr_max-q_snr_min
                                quality = round(((snr-q_snr_min)/(q_snr_span))*100,1)
                                if quality > 100.0: quality = 100.0
                                if quality < 0.0: quality = 0.0
                                self.r_stat_q = quality
                            except:
                                pass
                        elif (command == KISS.CMD_ST_ALOCK):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 2):
                                    at = command_buffer[0] << 8 | command_buffer[1]
                                    self.r_st_alock = at/100.0
                                    RNS.log(str(self)+" Radio reporting short-term airtime limit is "+str(self.r_st_alock)+"%", RNS.LOG_DEBUG)
                        elif (command == KISS.CMD_LT_ALOCK):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 2):
                                    at = command_buffer[0] << 8 | command_buffer[1]
                                    self.r_lt_alock = at/100.0
                                    RNS.log(str(self)+" Radio reporting long-term airtime limit is "+str(self.r_lt_alock)+"%", RNS.LOG_DEBUG)
                        elif (command == KISS.CMD_STAT_CHTM):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 11):
                                    ats = command_buffer[0] << 8 | command_buffer[1]
                                    atl = command_buffer[2] << 8 | command_buffer[3]
                                    cus = command_buffer[4] << 8 | command_buffer[5]
                                    cul = command_buffer[6] << 8 | command_buffer[7]
                                    crs = command_buffer[8]
                                    nfl = command_buffer[9]
                                    ntf = command_buffer[10]

                                    self.r_airtime_short      = ats/100.0
                                    self.r_airtime_long       = atl/100.0
                                    self.r_channel_load_short = cus/100.0
                                    self.r_channel_load_long  = cul/100.0
                                    self.r_current_rssi       = crs-RNodeInterface.RSSI_OFFSET
                                    self.r_noise_floor        = nfl-RNodeInterface.RSSI_OFFSET

                                    # TODO: Remove debug
                                    # interference_log_threshold = 10
                                    # if ntf == 0xFF:
                                    #     self.r_interference   = None
                                    #     if self.r_noise_floor != None:
                                    #         # Filter potential false interference events due to LNA recalibration
                                    #         if self.r_interference_l != None:
                                    #             if self.r_interference_l[1] < self.r_noise_floor+interference_log_threshold:
                                    #                 self.r_interference_l = None
                                    # else:
                                    #     if self.r_noise_floor != None:
                                    #         interference   = ntf-RNodeInterface.RSSI_OFFSET
                                    #         # Filter potential false interference events due to LNA recalibration
                                    #         if interference > self.r_noise_floor+interference_log_threshold:
                                    #             self.r_interference   = ntf-RNodeInterface.RSSI_OFFSET
                                    #             self.r_interference_l = [time.time(), self.r_interference]

                                    if ntf == 0xFF:
                                        self.r_interference   = None
                                    else:
                                        self.r_interference   = ntf-RNodeInterface.RSSI_OFFSET
                                        self.r_interference_l = [time.time(), self.r_interference]

                                    if self.r_interference != None:
                                        RNS.log(f"{self} Radio detected interference at {self.r_interference} dBm", RNS.LOG_DEBUG)

                                    # TODO: Remove debug
                                    # RNS.log(f"RSSI: {self.r_current_rssi}, Noise floor: {self.r_noise_floor}, Interference: {self.r_interference}", RNS.LOG_DEBUG)
                        elif (command == KISS.CMD_STAT_PHYPRM):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 12):
                                    lst = (command_buffer[0] << 8 | command_buffer[1])/1000.0
                                    lsr = command_buffer[2] << 8 | command_buffer[3]
                                    prs = command_buffer[4] << 8 | command_buffer[5]
                                    prt = command_buffer[6] << 8 | command_buffer[7]
                                    cst = command_buffer[8] << 8 | command_buffer[9]
                                    dft = command_buffer[10] << 8 | command_buffer[11]

                                    if lst != self.r_symbol_time_ms or lsr != self.r_symbol_rate or prs != self.r_preamble_symbols or prt != self.r_premable_time_ms or cst != self.r_csma_slot_time_ms or dft != self.r_csma_difs_ms:
                                        self.r_symbol_time_ms    = lst
                                        self.r_symbol_rate       = lsr
                                        self.r_preamble_symbols  = prs
                                        self.r_premable_time_ms  = prt
                                        self.r_csma_slot_time_ms = cst
                                        self.r_csma_difs_ms      = dft
                                        RNS.log(f"{self} Radio reporting symbol time is "+str(round(self.r_symbol_time_ms,2))+"ms ("+str(self.r_symbol_rate)+" baud)", RNS.LOG_DEBUG)
                                        RNS.log(f"{self} Radio reporting preamble is "+str(self.r_preamble_symbols)+" symbols ("+str(self.r_premable_time_ms)+"ms)", RNS.LOG_DEBUG)
                                        RNS.log(f"{self} Radio reporting CSMA slot time is "+str(self.r_csma_slot_time_ms)+"ms", RNS.LOG_DEBUG)
                                        RNS.log(f"{self} Radio reporting DIFS time is "+str(self.r_csma_difs_ms)+"ms", RNS.LOG_DEBUG)
                        elif (command == KISS.CMD_STAT_CSMA):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 3):
                                    cbw = command_buffer[0]
                                    cbl = command_buffer[1]
                                    cbh = command_buffer[2]

                                    if cbw != self.r_csma_cw_band or cbl != self.r_csma_cw_min or cbh != self.r_csma_cw_max:
                                        self.r_csma_cw_band = cbw
                                        self.r_csma_cw_min  = cbl
                                        self.r_csma_cw_max  = cbh
                                        # TODO: Remove debug
                                        # RNS.log(f"{self} Radio reporting contention window band is {self.r_csma_cw_band}", RNS.LOG_EXTREME)
                                        # RNS.log(f"{self} Radio reporting minimum contention window is {self.r_csma_cw_min}", RNS.LOG_EXTREME)
                                        # RNS.log(f"{self} Radio reporting maximum contention window is {self.r_csma_cw_max}", RNS.LOG_EXTREME)
                        elif (command == KISS.CMD_STAT_BAT):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 2):
                                    bat_percent = command_buffer[1]
                                    if bat_percent > 100:
                                        bat_percent = 100
                                    if bat_percent < 0:
                                        bat_percent = 0
                                    self.r_battery_state   = command_buffer[0]
                                    self.r_battery_percent = bat_percent
                        elif (command == KISS.CMD_STAT_TEMP):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 1):
                                    temp = command_buffer[0]-120
                                    if temp >= -30 and temp <= 90: self.r_temperature = temp
                                    else:                          self.r_temperature = None
                                    self.cpu_temp = self.r_temperature
                        elif (command == KISS.CMD_RANDOM):
                            self.r_random = byte
                        elif (command == KISS.CMD_PLATFORM):
                            self.platform = byte
                        elif (command == KISS.CMD_MCU):
                            self.mcu = byte
                        elif (command == KISS.CMD_ERROR):
                            if (byte == KISS.ERROR_INITRADIO):
                                RNS.log(str(self)+" hardware initialisation error (code "+RNS.hexrep(byte)+")", RNS.LOG_ERROR)
                                raise IOError("Radio initialisation failure")
                            elif (byte == KISS.ERROR_TXFAILED):
                                RNS.log(str(self)+" hardware TX error (code "+RNS.hexrep(byte)+")", RNS.LOG_ERROR)
                                raise IOError("Hardware transmit failure")
                            elif (byte == KISS.ERROR_MEMORY_LOW):
                                RNS.log(str(self)+" hardware error (code "+RNS.hexrep(byte)+"): Memory exhausted", RNS.LOG_ERROR)
                                self.hw_errors.append({"error": KISS.ERROR_MEMORY_LOW, "description": "Memory exhausted on connected device"})
                            elif (byte == KISS.ERROR_MODEM_TIMEOUT):
                                RNS.log(str(self)+" hardware error (code "+RNS.hexrep(byte)+"): Modem communication timed out", RNS.LOG_ERROR)
                                self.hw_errors.append({"error": KISS.ERROR_MODEM_TIMEOUT, "description": "Modem communication timed out on connected device"})
                            else:
                                RNS.log(str(self)+" hardware error (code "+RNS.hexrep(byte)+")", RNS.LOG_ERROR)
                                raise IOError("Unknown hardware failure")
                        elif (command == KISS.CMD_RESET):
                            if (byte == 0xF8):
                                if self.platform == KISS.PLATFORM_ESP32:
                                    if self.online:
                                        RNS.log("Detected reset while device was online, reinitialising device...", RNS.LOG_ERROR)
                                        raise IOError("ESP32 reset")
                        elif (command == KISS.CMD_READY):
                            self.process_queue()
                        elif (command == KISS.CMD_FB_READ):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 512):
                                    self.r_framebuffer_latency = time.time() - self.r_framebuffer_readtime
                                    self.r_framebuffer = command_buffer

                        elif (command == KISS.CMD_DISP_READ):
                            if (byte == KISS.FESC):
                                escape = True
                            else:
                                if (escape):
                                    if (byte == KISS.TFEND):
                                        byte = KISS.FEND
                                    if (byte == KISS.TFESC):
                                        byte = KISS.FESC
                                    escape = False
                                command_buffer = command_buffer+bytes([byte])
                                if (len(command_buffer) == 1024):
                                    self.r_disp_latency = time.time() - self.r_disp_readtime
                                    self.r_disp = command_buffer

                        elif (command == KISS.CMD_DETECT):
                            if byte == KISS.DETECT_RESP:
                                self.detected = True
                            else:
                                self.detected = False

                    self._parser_progress()
                    yield True
                else:
                    yield False

        except Exception as error:
            self._transport_error(str(error))
