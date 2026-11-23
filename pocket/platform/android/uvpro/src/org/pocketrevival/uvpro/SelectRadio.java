package org.pocketrevival.uvpro;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.widget.Toast;
import java.util.ArrayList;

public final class SelectRadio extends Activity {
    private int port;
    private String token;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        port = getIntent().getIntExtra("port", 0);
        token = getIntent().getStringExtra("token");
        if (port < 1 || port > 65535 || token == null || !token.matches("[0-9a-f]{48}")) {
            finish(); return;
        }
        if (android.os.Build.VERSION.SDK_INT >= 31 && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.BLUETOOTH_CONNECT}, 1);
        } else choose();
    }

    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] grants) {
        super.onRequestPermissionsResult(code, permissions, grants);
        if (code == 1 && grants.length > 0 && grants[0] == PackageManager.PERMISSION_GRANTED) choose();
        else finish();
    }

    private void choose() {
        BluetoothAdapter adapter = getSystemService(BluetoothManager.class).getAdapter();
        if (adapter == null || !adapter.isEnabled()) {
            Toast.makeText(this, "Enable Bluetooth in Android settings", Toast.LENGTH_LONG).show();
            finish(); return;
        }
        ArrayList<BluetoothDevice> devices = new ArrayList<>(adapter.getBondedDevices());
        String[] names = new String[devices.size()];
        for (int i = 0; i < names.length; i++) {
            BluetoothDevice device = devices.get(i);
            names[i] = device.getName() + " · " + device.getAddress();
        }
        AlertDialog.Builder dialog = new AlertDialog.Builder(this)
            .setTitle("Receive in Pocket from a paired radio")
            .setNegativeButton("Cancel", (d, w) -> finish())
            .setOnCancelListener(d -> finish());
        if (devices.isEmpty()) dialog.setMessage("Pair the UV-PRO in Android Bluetooth settings first.");
        else dialog.setItems(names, (d, i) -> {
            Intent intent = new Intent(this, ReceiveService.class)
                .putExtra("address", devices.get(i).getAddress())
                .putExtra("port", port).putExtra("token", token);
            startForegroundService(intent);
            finish();
        });
        dialog.show();
    }
}
