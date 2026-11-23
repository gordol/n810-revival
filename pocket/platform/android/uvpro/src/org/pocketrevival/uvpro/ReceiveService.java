package org.pocketrevival.uvpro;

import android.app.*;
import android.bluetooth.*;
import android.content.Intent;
import android.os.IBinder;
import android.widget.Toast;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

public final class ReceiveService extends Service {
    private static final UUID SERIAL = UUID.fromString("00001101-0000-1000-8000-00805f9b34fb");
    private Session active;

    private final class Session implements Closeable {
        final Socket phone = new Socket();
        final BluetoothSocket radio;
        final int id;
        Session(String address, int id) throws IOException {
            this.id = id;
            BluetoothAdapter adapter = getSystemService(BluetoothManager.class).getAdapter();
            radio = adapter.getRemoteDevice(address).createRfcommSocketToServiceRecord(SERIAL);
        }
        public void close() {
            try { phone.close(); } catch (IOException ignored) {}
            try { radio.close(); } catch (IOException ignored) {}
        }
        void receive(int port, String token) {
            try {
                phone.connect(new InetSocketAddress("127.0.0.1", port), 3000);
                OutputStream dest = phone.getOutputStream();
                dest.write((token + "\n").getBytes(StandardCharsets.US_ASCII));
                // A closed Pocket view/connection must release even a silent radio.
                new Thread(() -> {
                    try { phone.getInputStream().read(); } catch (IOException ignored) {}
                    close();
                }, "Pocket lifetime").start();
                android.os.Handler handler = new android.os.Handler(getMainLooper());
                Runnable timeout = () -> { try { radio.close(); } catch (IOException ignored) {} };
                handler.postDelayed(timeout, 20000);
                try {
                    radio.connect();
                } catch (IOException | SecurityException error) {
                    dest.write("FAILED\n".getBytes(StandardCharsets.US_ASCII));
                    throw error;
                } finally {
                    handler.removeCallbacks(timeout);
                }
                dest.write("READY\n".getBytes(StandardCharsets.US_ASCII));
                InputStream source = radio.getInputStream();
                byte[] buffer = new byte[8192];
                int length;
                while ((length = source.read(buffer)) != -1) dest.write(buffer, 0, length);
            } catch (IOException | SecurityException error) {
                getMainExecutor().execute(() -> {
                    if (active == this) Toast.makeText(ReceiveService.this,
                        "Radio connection ended: " + error.getMessage(), Toast.LENGTH_LONG).show();
                });
            } finally {
                close();
                stopSelf(id);
            }
        }
    }

    @Override public int onStartCommand(Intent intent, int flags, int id) {
        if (intent == null || "stop".equals(intent.getAction())) { stopSelf(); return START_NOT_STICKY; }
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("rx", "Radio reception", NotificationManager.IMPORTANCE_LOW));
        PendingIntent stop = PendingIntent.getService(this, 0, new Intent(this, ReceiveService.class).setAction("stop"),
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        startForeground(1, new Notification.Builder(this, "rx").setContentTitle("Pocket UV-PRO receiver")
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentText("Receiving for Pocket on this phone").addAction(0, "Stop", stop).build());
        if (active != null) active.close();
        try {
            Session session = new Session(intent.getStringExtra("address"), id);
            active = session;
            new Thread(() -> session.receive(intent.getIntExtra("port", 0), intent.getStringExtra("token")), "Pocket serial").start();
        } catch (IOException | RuntimeException error) { stopSelf(id); }
        return START_NOT_STICKY;
    }
    @Override public IBinder onBind(Intent intent) { return null; }
    @Override public void onDestroy() { if (active != null) active.close(); active = null; super.onDestroy(); }
}
