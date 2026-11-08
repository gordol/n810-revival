# Doom / Freedoom

Prepare the optional game from `pocket/` with `make doom`. This builds the
bundled DoomGeneric engine and its small frame/input bridge, then downloads
Freedoom 0.13.0 into the user's cache if it is missing. The download is explicit
and its archive is verified against a pinned SHA-256. Opening the app never
starts a download.

To reuse existing data offline:

```sh
make doom EXTRA='--wad /path/to/freedoom1.wad --no-download'
```

The app keeps a reference to that WAD rather than making a second copy. Build
outputs and game data stay out of Git. `build/BUILD.json` records the engine,
bridge, compiler arguments and selected data identities. Set `CC` or pass
`--cc` when building for another target; a host executable cannot run on Nokia.

The same engine and input/lifecycle owner serve both frontends. In the terminal,
the native bridge produces RGB half-block cells. In the GUI, it converts the
latest complete engine frame directly to a bounded RGB565 image. Click inside the GUI game view to capture the pointer. Horizontal mouse motion
turns, and the left button fires. Escape releases the pointer before a subsequent
Escape opens the game menu. Switching away releases capture and held buttons.
The game
engine itself renders in software; pixel presentation does not imply GPU game
rendering. Resizing preserves the intended 4:3 image. Losing focus releases held
keys and pauses the child; closing and reopening the window resumes this desktop
session. Exiting Pocket reaps the child. Audio is disabled.

DoomGeneric is upstream GPL-covered code derived from Doom and Chocolate Doom.
Its unmodified source and notices live in `vendor/doomgeneric/`; `SOURCE.json`
records the retained source identity. Those upstream notices and rights remain
in force. Pocket's bridge, build script and graphical adapter use GPL-2.0-or-later.
Freedoom is separate game data, obtained only by the explicit preparation step;
its COPYING and credit files are retained alongside the cached WAD. No original
commercial Doom data is included.
