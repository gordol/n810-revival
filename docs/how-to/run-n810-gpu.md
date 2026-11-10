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

The platform's console init service runs the Pocket boot hook. That hook uses
the same supervisor and saved renderer selection. Check the installed entry:

```sh
sudo cat /etc/boot.d/90-n810-pocket
```

For building the driver, use [Build MBX and Mesa](build-graphics.md).
