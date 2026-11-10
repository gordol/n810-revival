# Run Symbian applications on the N810

Use the managed GPU desktop with the Symbian launcher installed. The runtime
expects these private files under `~/.local/share/symbian-private/`:

- `code/symbian-runtime`: the native ARM runtime.
- `code/lib/libOSMesa.so.8`: its matching MBX Mesa library.
- `runtime/`: the system libraries, resources and installed applications.

Users supply their own compatible system libraries and application installers.

## From Pocket

Open **Symbian** in the application menu. Choose an installed application
with the arrows and press Enter. The application takes the display; exiting it returns to the saved
Pocket desktop.

Use the arrow keys to move and Enter to select. Menu/F1 is the left softkey;
Esc/F2 is the right softkey. In ChessGenius, return to the main menu and choose
its **Exit** softkey to close the application.

## Add applications

Copy `.sis` or `.sisx` installers into:

```text
~/.local/share/symbian-private/runtime/inbox/
```

SFTP works over Wi-Fi or USB networking (`192.168.10.1`, user `nokia`). In
Pocket's Symbian launcher, press **R**, select **Install: filename**, and press
Enter. Refresh afterward to list the installed application.

The runtime maintains its own Symbian application registry. Pocket has one
Symbian launcher; individual guest applications stay in the Symbian list.

## From Make

With Pocket running, open an SSH session to the N810. From the repository:

```sh
cd pocket
make symbian APP=chess
```

Use `APP=snakes` to select Snakes. Make sends the same request as the Pocket
launcher. The supervisor serializes application and desktop rendering.

To install a package from an existing local path on the Nokia:

```sh
make symbian-install PACKAGE=/path/to/application.sisx
```

The launcher also accepts installed app UIDs, for example `APP=2000730f`.
