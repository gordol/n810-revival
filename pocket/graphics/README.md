# Build and run the graphical desktop

Pocket has a graphical frontend for Mac/Linux and a managed framebuffer frontend
for the N810. Both use the same desktop and applications.

## On the N810

Follow [Set up an N810](../../docs/start.md), then
[Start the GPU desktop](../../docs/how-to/run-n810-gpu.md).

## On Mac or Linux

Install Python 3.11 or newer, Make, a C compiler, Python development headers,
SDL2 and OpenGL development libraries.

On macOS, install the Command Line Tools and SDL2:

```sh
xcode-select --install
brew install sdl2
```

On Debian:

```sh
sudo apt-get install build-essential python3-dev libsdl2-dev libgl1-mesa-dev
```

From the repository root:

```sh
cd pocket
make gui
```

The first launch builds the native libraries in `build/graphics/`, then opens
Pocket. Later launches reuse the build. Close the window to quit.

On Apple Silicon, GPU map and background effects use Python 3.12 or newer and:

```sh
python3 -m pip install -r requirements-graphics-macos.txt
make gui
```

To select CPU map and background effects:

```sh
make gui EXTRA='--effect-backend cpu'
```

## Controls

Use the desktop menu to open applications. Drag a window by its title bar and
resize it at its border. Open Help for keyboard controls.

In Surface Room, use the movement controls shown in Help. G toggles the target
game, R resets it, and Escape releases the pointer.

For font choices, select `--font-mode smooth`, `crisp`, or `console` through
`EXTRA`. For example:

```sh
make gui EXTRA='--font-mode console'
```
