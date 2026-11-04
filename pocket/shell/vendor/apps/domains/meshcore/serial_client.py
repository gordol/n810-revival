"""Official MeshCore client with a PTY transport for local bridge adapters.

PTYs have no DTR/RTS modem lines. The upstream serial protocol unconditionally
sets those lines in connection_made, which fails with ENOTTY on macOS. Only
recognized local PTYs use this override; physical radios retain upstream setup.
"""
import re
import asyncio
import sys
from pathlib import Path


def bridge_status(phase='starting', previous=None):
    return dict(kind='htit', phase=phase, observed_at=(previous or {}).get('observed_at'),
                classic_connected=False if phase=='stopped' else None,
                ble_connected=None, ble_ready=None, mtu=None, owner=None,
                spp1=None, spp2=None, lease_ack_at=None)


def parse_bridge_status(line):
    if not line.startswith(b'HUB_STATUS=') or len(line)>256:return None
    fields=line[len(b'HUB_STATUS='):].strip().split(b',')
    if len(fields)!=10 or fields[0]!=b'1':return None
    try:
        observed=float(fields[1])
        lease=float(fields[9]) if fields[9] else None
        if not 0<observed<1e12 or (lease is not None and not 0<lease<1e12):return None
        if any(fields[i] not in (b'0',b'1') for i in (2,3,4,7,8)):return None
        mtu,owner=int(fields[5]),int(fields[6])
        if not 0<=mtu<=517 or not 0<=owner<=255:return None
    except (ValueError,OverflowError):return None
    return dict(kind='htit',phase='online',observed_at=observed,
                classic_connected=fields[2]==b'1',ble_connected=fields[3]==b'1',
                ble_ready=fields[4]==b'1',mtu=mtu,owner=owner,
                spp1=fields[7]==b'1',spp2=fields[8]==b'1',lease_ack_at=lease)


async def create_serial_client(port, baudrate=115200, bridge_status_callback=None, **options):
    attachment=None
    connection=None
    status=bridge_status()
    loop=asyncio.get_running_loop()
    def publish(row):
        nonlocal status
        status=row
        if bridge_status_callback:bridge_status_callback(dict(row))
    def hub_changed():
        if attachment is None or attachment.closed:return
        try:
            state=attachment.snapshot()
            row=dict(state.get('bridge',{}),kind='htit',phase=state['connection_state'],
                     classic_connected=state['connection_state']=='online',hub_id=state['hub_id'],
                     generation=state['generation'],service_state='ready')
            for item in state.get('attachments',()):
                if item.get('state')=='ready' and item.get('service') in (2,3):
                    row['peer_port' if item['service']==2 else 'rnode_port']=item['port']
            publish(row)
        except (OSError,ValueError) as error:
            publish(dict(status,phase='error',service_state='error',error=str(error)))
            if connection is not None and connection.transport is not None:connection.transport.close()
    if port.startswith('htit://'):
        match=re.fullmatch(r'htit://((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})/([0-9]{1,2})/((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})/([01])',port)
        if not match or not 1<=int(match[2])<=30:raise ValueError('Invalid HTIT bridge address')
        import threading
        sys.path.insert(0,str(Path(__file__).resolve().parents[4]))
        from vendor.apps.domains.meshcore.hub_provider import attach_hub
        stopped=threading.Event()
        task=asyncio.create_task(asyncio.to_thread(attach_hub,1,port=f'rfcomm://{match[1]}/{match[2]}',
            ble=match[3],address_type=int(match[4]),timeout=75,stopped=stopped))
        try:
            # Submit the existing hub worker before loading the optional SDK.
            await asyncio.sleep(0)
            from meshcore import MeshCore
            from meshcore.serial_cx import SerialConnection
            attachment=await asyncio.shield(task)
        except BaseException:
            stopped.set()
            try:
                unfinished=await task
                await asyncio.to_thread(unfinished.close)
            except (OSError,ValueError,InterruptedError):pass
            publish(bridge_status('stopped',status))
            raise
        port=attachment.port
        def wakeup():
            try:loop.call_soon_threadsafe(hub_changed)
            except RuntimeError:pass  # The client event loop has already closed.
        attachment.provider.bind_wakeup(wakeup)
        hub_changed()

    if attachment is None:
        from meshcore import MeshCore
        from meshcore.serial_cx import SerialConnection

    if not re.fullmatch(r'/dev/(?:pts/[0-9]+|ttys[0-9]+)', port):
        return await MeshCore.create_serial(port, baudrate, **options)

    class PtyConnection(SerialConnection):
        async def disconnect(self):
            try:
                await super().disconnect()
            finally:
                if attachment:
                    await asyncio.to_thread(attachment.close)
                    publish(dict(status,service_state='detached',ble_ready=False,ble_connected=False,lease_ack_at=None))

        class MCSerialClientProtocol(SerialConnection.MCSerialClientProtocol):
            def connection_made(self, transport):
                self.cx.transport = transport
                self.cx._connected_event.set()

    connection = PtyConnection(port, baudrate)
    client = MeshCore(connection, **options)
    try:
        if await client.connect() is not None:
            return client
    except BaseException:
        await client.disconnect()
        raise
    await client.disconnect()
    return None
