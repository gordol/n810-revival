# Start the GPU desktop on the N810

Use an N810 with the project's Debian platform, matching kernel and graphics
release, and Pocket supervisor installed. For a new tablet, begin with
[Set up an N810](../start.md).

## Start Pocket

The current internal and SD kits use SysV init. With Pocket stopped, run from
the tablet console or an SSH session:

```sh
sudo /etc/init.d/pocket-desktop start
```

The supervisor checks the selected graphics release, starts the GPU service and
opens Pocket on the tablet display. Exit Pocket through its desktop menu to
return to the previous console. Press `b` on the desktop to toggle its background.

## Check the selected renderer

```sh
readlink /usr/local/lib/n810-graphics/current
sudo /etc/init.d/pocket-desktop status
```

Graphics releases live under `/usr/local/lib/n810-graphics/releases/`; `current`
selects the active version. A release includes matching Mesa, the GPU module,
and frontend libraries. Keep the previous release when applying a graphics
update so it can be selected again after Pocket exits. A graphics-only update
does not require rewriting storage or flashing the kernel when the module is
built against that installed kernel's symbol versions.

The supervisor archives session output and exit reports under
`/var/log/n810-pocket-native/`. Reading those records requires root. A successful
GPU build or kit check does not establish physical display acceptance: test the
normal launcher, background toggle, and clean return to the console on the tablet.

## Startup after boot

The current kits register `pocket-desktop` with SysV init. They do not provide
`systemctl`. Older installations may instead have the
`/usr/local/sbin/n810-pocket-console` launcher or a systemd service; check the
installed init system before using commands intended for those releases.

For building the driver, use [Build MBX and Mesa](build-graphics.md).
