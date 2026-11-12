# Start the GPU desktop on the N810

Use an N810 with the project's Debian platform, matching kernel and graphics
release, and Pocket supervisor installed. For a new tablet, begin with
[Set up an N810](../start.md).

## Start Pocket

With the console free, run on the N810:

```sh
sudo /usr/local/sbin/n810-pocket-console run
```

The supervisor checks the selected graphics release, starts the GPU service and
opens Pocket on the display. Exit Pocket through its desktop menu to return to
the previous console.

## Check the selected renderer

```sh
cat /usr/local/lib/n810-pocket/renderer
sudo /usr/local/sbin/n810-pocket-console status
```

The saved value `gpu` selects the graphical desktop. Graphics releases live under
`/usr/local/lib/n810-graphics/`; `current` selects the active version.

## Startup after boot

On SysV installations, `rc.local` runs the Pocket boot hook when it is
installed. Check the hook and saved renderer before relying on automatic
startup:

```sh
test -x /etc/boot.d/90-n810-pocket && cat /etc/boot.d/90-n810-pocket
cat /usr/local/lib/n810-pocket/renderer
```

The fresh internal image uses `pocket-desktop.service` under systemd instead.
Check its active state and the running desktop on that tablet after boot.

For building the driver, use [Build MBX and Mesa](build-graphics.md).
