"""Event-driven serial and BLE adapter for the pinned official RNS interface."""

import asyncio
import hashlib
import os
from pathlib import Path
import queue
import threading

import RNS.Interfaces.RNodeInterface as upstream

from connection import Connection
from parser import Parser


SOURCE_SHA256 = '2530b947599889a96f2b8af6b661c71e0840656cc5daa19584b86301fc9f0855'
OfficialRNode = upstream.RNodeInterface
KISS = upstream.KISS


class QueuedSerial:
    def __init__(self, raw, owner):
        self.raw, self.owner = raw, owner
        self.pending = queue.Queue(maxsize=128)
        self.tail = b''
        self.current = None
        self.incoming = bytearray()

    @property
    def in_waiting(self):
        return len(self.incoming)

    def read(self, count):
        data = bytes(self.incoming[:count])
        del self.incoming[:count]
        return data

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def write(self, data):
        if not self.raw.is_open or self.owner.detached:
            raise OSError('Serial interface is closed')
        if len(data) > 65536:
            raise ValueError('Serial write exceeds queue limit')
        self.pending.put_nowait(bytes(data))
        self.owner.loop.call_soon_threadsafe(self.arm)
        return len(data)

    def arm(self):
        if self.raw.is_open and not self.owner.detached:
            self.owner.loop.add_writer(self.raw.fileno(), self.flush)

    def flush(self):
        if self.owner.detached:
            self.owner._cancel()
            return
        try:
            while True:
                if not self.tail:
                    try:
                        self.tail = self.pending.get_nowait()
                    except queue.Empty:
                        self.owner.loop.remove_writer(self.raw.fileno())
                        return
                    self.current = self.tail
                try:
                    count = os.write(self.raw.fileno(), self.tail)
                except BlockingIOError:
                    return
                if count == 0:
                    raise OSError('Serial write returned zero')
                self.tail = self.tail[count:]
                if not self.tail:
                    self.owner._command_written(self.current)
                    self.current = None
        except Exception as error:
            self.owner._transport_error(str(error))

    def close(self):
        self.owner.loop.call_soon_threadsafe(self.owner._shutdown)


class EventRNode(Parser, OfficialRNode):
    READ_BUDGET = 4096

    def __init__(self, owner, configuration):
        self.loop = asyncio.new_event_loop()
        self.connection = None
        self.on_status = getattr(type(self), 'status_callback', lambda event: None)
        self._reported = {}
        self._thread = None
        self._generation = None
        self._serial_closed = False
        self._eligible_fields = set()
        super().__init__(owner, configuration)

    def open_port(self):
        if self.use_ble:
            from ble_transport import BLESerial
            self.serial = BLESerial(self, self.ble_name or self.ble_addr)
            # The upstream constructor checks handle existence before starting
            # asynchronous configuration. Radio readiness remains event-driven.
            self.serial.is_open = True
            return
        if self.use_tcp:
            raise ValueError('Event RNode adapter does not support TCP')
        super().open_port()
        self.serial = QueuedSerial(self.serial, self)

    def configure_device(self):
        self.reset_radio_state()
        self.connection = Connection(dict(frequency=self.frequency, bandwidth=self.bandwidth,
                                    txpower=self.txpower, sf=self.sf, cr=self.cr, state=1),
                                    lambda generation: self.detect(),
                                    lambda generation, values: self._configure_radio(),
                                    lambda generation: self._shutdown(), self._status)
        self._parser = self.parser_events()
        if self.use_ble:
            self.serial.is_open = False
            self.loop.call_soon(self.serial.start)
        else:
            self.loop.add_reader(self.serial.fileno(), self._read_ready)
            self.loop.call_soon(self.connection.start)
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        try:
            self.loop.run_forever()
        finally:
            self._shutdown()
            self.loop.close()

    def _status(self, phase, error):
        self.online = self.interface_ready = phase == 'ready'
        self.on_status(dict(phase=phase, error=error, name=self.name,
                            readbacks=dict(self.connection.replies)))

    def _read_ready(self):
        try:
            try:
                data = os.read(self.serial.fileno(), self.READ_BUDGET)
            except BlockingIOError:
                return
            if not data:
                self._transport_error('Serial stream closed')
                return
            self._consume(data)
        except Exception as error:
            self._transport_error(str(error))

    def _consume(self, data):
        try:
            if self._serial_closed:
                return
            if len(self.serial.incoming) + len(data) > 65536:
                raise ValueError('RNode receive buffer exceeds limit')
            self.serial.incoming.extend(data)
            for _ in range(len(data)):
                if self._serial_closed or not next(self._parser):
                    break
        except StopIteration:
            if not self._serial_closed:
                self._transport_error('Serial parser stopped')
        except Exception as error:
            self._transport_error(str(error))

    def _parser_progress(self):
        connection = self.connection
        if connection.phase == 'detecting' and self.detected and self.firmware_ok and self.platform is not None:
            if self.platform in (KISS.PLATFORM_ESP32, KISS.PLATFORM_NRF52):
                self.display = True
            connection.detected(connection.generation)
        if connection.phase == 'configuring':
            for field in tuple(self._eligible_fields):
                value = getattr(self, 'r_' + field)
                if value is not None and self._reported.get(field) != value:
                    self._reported[field] = value
                    connection.readback(connection.generation, field, value)

    def _clear_readbacks(self):
        self._reported.clear()
        for field in Connection.fields:
            setattr(self, 'r_' + field, None)

    def _configure_radio(self):
        self._eligible_fields.clear()
        self._clear_readbacks()
        self.setFrequency()
        self.setBandwidth()
        self.setTXPower()
        self.setSpreadingFactor()
        self.setCodingRate()
        self.setSTALock()
        self.setLTALock()
        self.setRadioState(KISS.RADIO_STATE_ON)

    def _command_written(self, data):
        if self.connection.phase != 'configuring' or len(data) < 2 or data[0] != KISS.FEND:
            return
        field = {KISS.CMD_FREQUENCY: 'frequency', KISS.CMD_BANDWIDTH: 'bandwidth',
                 KISS.CMD_TXPOWER: 'txpower', KISS.CMD_SF: 'sf',
                 KISS.CMD_CR: 'cr', KISS.CMD_RADIO_STATE: 'state'}.get(data[1])
        if field is not None:
            setattr(self, 'r_' + field, None)
            self._reported.pop(field, None)
            self._eligible_fields.add(field)

    def validate_firmware(self):
        self.firmware_ok = (self.maj_version > self.REQUIRED_FW_VER_MAJ or
                            self.maj_version == self.REQUIRED_FW_VER_MAJ and
                            self.min_version >= self.REQUIRED_FW_VER_MIN)
        if not self.firmware_ok:
            self._transport_error('Unsupported RNode firmware version')

    def _transport_error(self, error):
        if self.connection and self.connection.phase != 'idle':
            self.connection.failed(self.connection.generation, error)
        elif self.connection:
            self._status('failed', error)
            self._shutdown()
        else:
            self.on_status(dict(phase='failed', error=error, name=self.name, readbacks={}))
            self.loop.close()

    def reconnect_port(self):
        self._transport_error('Serial open failed; explicit Connect required')

    def _close_serial(self):
        if self._serial_closed:
            return
        self._serial_closed = True
        self.online = self.interface_ready = False
        raw = getattr(self.serial, 'raw', self.serial)
        if raw is not None and raw.is_open:
            fd = raw.fileno()
            self.loop.remove_reader(fd)
            self.loop.remove_writer(fd)
            raw.close()
        self.loop.stop()

    def detach(self):
        self.detached = True
        if not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self._cancel)

    def _cancel(self):
        if self.connection:
            self.connection.cancel()
        self._shutdown()

    def _shutdown(self):
        if self._serial_closed:
            return
        self.detached = True
        if self.use_ble:
            self.serial.shutdown()
            return
        if isinstance(self.serial, QueuedSerial):
            self.serial.tail = b''
            self.serial.current = None
            while True:
                try:
                    self.serial.pending.get_nowait()
                except queue.Empty:
                    break
        raw = getattr(self.serial, 'raw', self.serial)
        if raw is not None and raw.is_open:
            # Attempt the official shutdown commands without waiting or replaying
            # queued payloads. Port closure does not prove radio-state readback.
            try:
                os.write(raw.fileno(), bytes([KISS.FEND, KISS.CMD_RADIO_STATE, KISS.RADIO_STATE_OFF,
                         KISS.FEND, KISS.CMD_LEAVE, 0xFF, KISS.FEND]))
            except OSError:
                pass
        self._close_serial()


def install(status_callback):
    if hashlib.sha256(Path(upstream.__file__).read_bytes()).hexdigest() != SOURCE_SHA256:
        raise RuntimeError('Event RNode adapter requires the exact reviewed upstream source')
    EventRNode.status_callback = staticmethod(status_callback)
    upstream.RNodeInterface = EventRNode
