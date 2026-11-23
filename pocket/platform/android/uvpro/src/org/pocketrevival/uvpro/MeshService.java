package org.pocketrevival.uvpro;

import android.app.*;
import android.bluetooth.*;
import android.content.Intent;
import android.os.IBinder;
import java.io.*;
import java.net.*;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

/** One MeshCore companion packet per Nordic UART write or notification. */
public final class MeshService extends Service {
    private static final UUID SERVICE = nus(1), RX = nus(2), TX = nus(3);
    private static final UUID CCCD = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    private Session active;

    private static UUID nus(int n) {
        return UUID.fromString("6e40000" + n + "-b5a3-f393-e0a9-e50e24dcca9e");
    }

    private final class Session extends BluetoothGattCallback {
        final Socket phone = new Socket();
        final ArrayBlockingQueue<String> events = new ArrayBlockingQueue<>(8);
        volatile BluetoothGatt gatt;
        volatile int mtu = 23;
        volatile boolean ready, closed;
        DataOutputStream output;

        void signal(String event, int status) {
            if (status != BluetoothGatt.GATT_SUCCESS || !events.offer(event)) close();
        }

        void await(String event, boolean started) throws IOException, InterruptedException {
            if (!started || !event.equals(events.poll(12, TimeUnit.SECONDS)))
                throw new IOException("Bluetooth operation failed: " + event);
        }

        void close() {
            closed = true;
            try { phone.close(); } catch (IOException ignored) {}
            events.offer("closed");
            BluetoothGatt link = gatt;
            if (link != null) link.close();
        }

        @Override public void onConnectionStateChange(BluetoothGatt link, int status, int state) {
            if (state == BluetoothProfile.STATE_CONNECTED) signal("connected", status);
            else if (state == BluetoothProfile.STATE_DISCONNECTED) close();
        }
        @Override public void onMtuChanged(BluetoothGatt link, int size, int status) {
            mtu = size;
            signal("mtu", status);
        }
        @Override public void onServicesDiscovered(BluetoothGatt link, int status) {
            signal("services", status);
        }
        @Override public void onDescriptorWrite(BluetoothGatt link, BluetoothGattDescriptor desc, int status) {
            if (CCCD.equals(desc.getUuid()) && status == BluetoothGatt.GATT_SUCCESS) {
                synchronized (this) {
                    try { output.writeBytes("READY\n"); ready = true; }
                    catch (IOException error) { close(); return; }
                }
            }
            signal("subscribed", status);
        }
        @Override public void onCharacteristicWrite(BluetoothGatt link, BluetoothGattCharacteristic ch, int status) {
            if (RX.equals(ch.getUuid())) signal("write", status);
        }
        @Override public void onCharacteristicChanged(BluetoothGatt link, BluetoothGattCharacteristic ch) {
            notification(ch, ch.getValue());
        }
        @Override public void onCharacteristicChanged(BluetoothGatt link, BluetoothGattCharacteristic ch, byte[] data) {
            notification(ch, data);
        }
        synchronized void notification(BluetoothGattCharacteristic ch, byte[] data) {
            if (!ready || !TX.equals(ch.getUuid())) return;
            if (data == null || data.length == 0 || data.length > 512) { close(); return; }
            try { output.writeShort(data.length); output.write(data); }
            catch (IOException error) { close(); }
        }

        void run(Intent intent, int id) {
            try {
                phone.connect(new InetSocketAddress("127.0.0.1", intent.getIntExtra("port", 0)), 3000);
                output = new DataOutputStream(phone.getOutputStream());
                output.writeBytes(intent.getStringExtra("token") + "\n");
                BluetoothAdapter adapter = getSystemService(BluetoothManager.class).getAdapter();
                BluetoothDevice device = adapter.getRemoteDevice(intent.getStringExtra("address"));
                gatt = device.connectGatt(MeshService.this, false, this, BluetoothDevice.TRANSPORT_LE);
                await("connected", gatt != null && !closed);
                await("mtu", gatt.requestMtu(517));
                await("services", gatt.discoverServices());
                BluetoothGattService service = gatt.getService(SERVICE);
                if (service == null) throw new IOException("MeshCore UART service missing");
                BluetoothGattCharacteristic rx = service.getCharacteristic(RX), tx = service.getCharacteristic(TX);
                if (rx == null || tx == null || !gatt.setCharacteristicNotification(tx, true))
                    throw new IOException("MeshCore UART characteristics missing");
                BluetoothGattDescriptor desc = tx.getDescriptor(CCCD);
                await("subscribed", desc != null && desc.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                    && gatt.writeDescriptor(desc));
                DataInputStream input = new DataInputStream(phone.getInputStream());
                rx.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);
                while (!closed) {
                    int length = input.readUnsignedShort();
                    if (length < 1 || length > Math.min(512, mtu - 3)) throw new IOException("Packet exceeds BLE MTU");
                    byte[] data = new byte[length];
                    input.readFully(data);
                    await("write", rx.setValue(data) && gatt.writeCharacteristic(rx));
                }
            } catch (IOException | RuntimeException | InterruptedException error) {
                // Socket EOF also reports link loss to the Pocket owner.
            } finally { close(); stopSelf(id); }
        }
    }

    @Override public int onStartCommand(Intent intent, int flags, int id) {
        if (intent == null || "stop".equals(intent.getAction())) { stopSelf(); return START_NOT_STICKY; }
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("mesh", "MeshCore", NotificationManager.IMPORTANCE_LOW));
        PendingIntent stop = PendingIntent.getService(this, 0, new Intent(this, MeshService.class).setAction("stop"),
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        startForeground(2, new Notification.Builder(this, "mesh").setContentTitle("Pocket MeshCore companion")
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth).addAction(0, "Disconnect", stop).build());
        if (active != null) active.close();
        Session session = new Session();
        active = session;
        new Thread(() -> session.run(intent, id), "Pocket MeshCore").start();
        return START_NOT_STICKY;
    }
    @Override public IBinder onBind(Intent intent) { return null; }
    @Override public void onDestroy() { if (active != null) active.close(); super.onDestroy(); }
}
