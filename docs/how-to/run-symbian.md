# Run Symbian applications on the N810

Use the managed GPU desktop with the Symbian launcher installed. The runtime
expects these private files under `~/.local/share/symbian-private/`:

- `code/symbian-runtime`: the native ARM runtime.
- `code/lib/libOSMesa.so.8`: its matching MBX Mesa library.
- `runtime/`: the system libraries, resources and installed applications.

Users supply their own compatible system libraries and application installers.

## From Pocket

Open **Symbian** in the application menu. Press Enter for ChessGenius or S for
Snakes. The application takes the display; exiting it returns to the saved
Pocket desktop.

Use the arrow keys to move and Enter to select. Menu/F1 is the left softkey;
Esc/F2 is the right softkey. In ChessGenius, return to the main menu and choose
its **Exit** softkey to close the application.

## From Make

With Pocket running, open an SSH session to the N810. From the repository:

```sh
cd pocket
make symbian APP=chess
```

Use `APP=snakes` to select Snakes. Make sends the same request as the Pocket
launcher. The supervisor serializes application and desktop rendering.
