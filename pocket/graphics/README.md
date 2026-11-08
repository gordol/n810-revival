# Pocket graphical frontend

The graphical frontend runs the same Pocket desktop, app registry, settings,
connections and window lifecycle as the terminal frontend. It presents native
pixels through SDL2/OpenGL. The desktop does not run inside a PTY or parse an ANSI
frame; terminal applications still own their normal PTYs.

## Build and run

Use Python 3.11 or newer, its development headers, a C compiler, SDL2 development
files and desktop OpenGL. On macOS, install the Command Line Tools and SDL2
(`brew install sdl2`). On Debian, the build dependencies are
`build-essential python3-dev libsdl2-dev libgl1-mesa-dev`.

From `pocket/`:

```sh
make graphics-native
make gui
```

The first command builds into the ignored `build/graphics/` directory. An
unchanged source/compiler/native-compositor identity reuses those outputs.
`make gui` checks the build automatically. `make tui` starts the terminal desktop.
No build step downloads map data, reads a captured desktop or connects to a Nokia.

On Apple Silicon, the default GPU effects/map kernels also need:

```sh
python3 -m pip install -r requirements-graphics-macos.txt
```

That pinned optional compute environment requires Python 3.12 or newer. To use
the portable OpenGL desktop with the existing CPU effect/map producers instead:

```sh
make gui EXTRA='--effect-backend cpu'
```

Both modes use GPU cell rasterization and direct GPU Room geometry. The optional
compute provider changes effect/map production; the terminal backend is unchanged.
A software GL renderer is rejected by default. `--allow-software` explicitly
admits one for tests; those results do not establish hardware performance.

## Text rendering

On macOS the GUI defaults to `--font-mode smooth`: Menlo's grayscale text
coverage is generated once at build time with CoreText. Native rendering uses
that coverage for text; box-drawing, terrain and fractional-block glyphs retain
the exact console bitmaps. Cached translucent window layers use the same font.
No font is rasterized by a Python loop during a frame.

Use `--font-mode crisp` for the same Menlo text with binary edges, or
`--font-mode console` for the original console bitmap. You can also set
`POCKET_GUI_FONT=console`. The font choice is a frontend context inherited by
all apps, not a mutable global font selection. The Nokia defaults to console
text at its physical 800×480 resolution. CoreText-generated font files are local
build outputs, not redistributed system-font files.

## Inputs and behavior

All native sources, the SDL input adapter, font conversion and room-mesh generator
are in this directory. `SOURCES.json` identifies the imported source snapshots.
The build converts the repository's reviewed console font without changing its
mapped glyph pixels, adds explicit UI glyphs, and generates the Room mesh from
`shell/apps/surface-renderer/room.py`. On macOS, missing UI characters receive a
build-time CoreText supplement. No experimental sibling checkout or `outputs/`
directory is needed. SDL2, OpenGL and optional MLX remain declared system/package
dependencies rather than copied binaries.

Resizing changes the desktop's actual grid and pixel canvas. Native raster work
uses bounded 400×400 tiles. Window text/chrome, shadows and cached overlays retain
the shared model's ordering. Surface Room produces direct geometry pixels and
keeps its walking controls; G toggles its target game, R resets it, and clicking
its viewport captures the pointer. Escape releases capture before returning to
normal app navigation. The Mac/Linux SDL input adapter shares those actions.

Station Map presents its existing terrain samples as pixels and draws roads
and streams from geographic vector segments with native clipping. Station
selection, labels, target previews, sidebar and input remain the shared model.
The adapter shares the existing bounded map worker; it does not add a polling
loop. Native vectors improve line drawing, while terrain sample resolution still
comes from the existing map renderer. Terrain tools and third-party map packs
retain their existing presentation.

Doom / Freedoom also uses a direct RGB565 image in the GUI, with the same
engine and lifecycle owner as the terminal app. Prepare it explicitly with
`make doom`; see [the game build notes](../shell/apps/doom-app/README.md).
Game data and compiled engines are local outputs, never implicit startup downloads.

The optional GPU-alpha composition candidate remains opt-in with
`POCKET_GPU_COMPOSE=1`. Default overlay composition uses C; this integration does
not change that performance choice or claim a new Nokia mixed-state GPU result.

## Verify

```sh
make graphics-check
python3 -m unittest discover -s tests -p 'test_graphical_frontend.py'
python3 -m unittest discover -s tests -p 'test_*pixel*.py'
```

The end-to-end check uses private temporary state and no attached services. It
opens the menu, Messages, Settings, Terminal and direct Room, resizes twice,
checks registry errors and output dimensions, and verifies no desktop ANSI/PTY.
For a Linux CI machine without a GPU:

```sh
xvfb-run -a python3 graphics/check.py --allow-software
```

The repository's release container builds the frontend from source, runs these
checks in explicit software GL mode and cross-builds the non-X ARM framebuffer
presenter with `graphics/build_nokia.py`. The latter needs
`arm-linux-gnueabi-gcc` or `CROSS_COMPILE`; it does not use a named local VM or
access a device. This integration's build and host tests do not establish Nokia
installation, framebuffer ownership or physical GPU acceptance.

See `PIXEL-INTERFACE.md` for the platform and native buffer contracts.

## Nokia framebuffer frontend

`build_nokia.py` can also build the GPU cell and Room renderer from these same
sources. Supply `--mesa-include` and `--mesa-library` for the verified ARM
Mesa/MBX build; their binary identity is recorded in `BUILD.json`. The ordinary
cross-build without those flags still builds the framebuffer presenter alone.
For a repository-contained Mesa build, use
`python3 graphics/mbx/build.py mesa --work /path/to/new-build --osmesa`
from the repository root. That adds `libOSMesa.so.8` and its development headers
to the ordinary Mesa package, using the same pinned download and sysroot once.
Build the matching `_cellengine.abi3.so` using `tools/build_native.py` and its
cached ARM Python headers.

`graphics/nokia.py` runs the shared desktop with that renderer and presenter.
Its launcher must provide an inherited framebuffer fd and an owned foreground
Linux VT on stdin. It does not load drivers, open the framebuffer by pathname,
change display modes or take a VT from another application. VT keyboard input,
touch, services and completions use the desktop's existing selector; idle has no
SDL pump or periodic frame poll. Display/service lifecycle belongs to the device
session owner. Build success alone is not physical-device acceptance.
