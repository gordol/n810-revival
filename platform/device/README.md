# Files installed on the N810

These are source templates for the tablet's root filesystem. They are not a
virtual machine. The matching commands are in `../scripts/`.

| Area | Files to start with |
|---|---|
| Power and display | `n810-charged.*`, `n810-powerd.init`, `n810-displayd.init`, `n810-backlightd.init`, `n810-wake.*`, `n810-ledd.init` |
| Input and console | `n810-buttons.map`, `n810-console.map`, `n810-keyboard.service`, `n810-fn-remap.service`, `n810-input-remap.service`, `n810-console-ux.init` |
| Connections | `debian-usb-interfaces`, `n810-wifi.*`, `n810-bluetooth-address.service`, `10-n810-address.conf` |
| Startup and policy | `n810-boot-mode.init`, `n810-zram.*`, `n810-power.sudoers`, `n810-idle.conf` |

Some devices use SysV init, some use systemd units, and a few files are
alternatives from different platform revisions. This source slice is not a
complete installer; check the exact target release before placing a file on
the tablet.
