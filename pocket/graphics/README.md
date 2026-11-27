# Build and run the graphical desktop

Pocket has a graphical frontend for Mac/Linux and a managed framebuffer frontend
for the N810. Both use the same desktop and applications.

## On the N810

Follow [Set up an N810](../../docs/start.md), then
[Start the GPU desktop](../../docs/how-to/run-n810-gpu.md).

## On Mac or Linux

Install Python 3.11 or newer, Make, a C compiler, Python development headers,
SDL2 and OpenGL development libraries.

On macOS, install Homebrew and the Xcode Command Line Tools. From the
repository root or `pocket/`, run:

```sh
make explore
```

This prepares the Sound, Hoh and Rainier terrain, reuses cached terrain on later
runs, and opens Rainier Walk. Choose **Explore** in the app for flights, ferries
and other outings. Use `make gui` to open the full desktop. Both commands set up
SDL2 and a local Python environment on the Mac. Apple Silicon uses the GPU for
map and background effects by default. The 3D scene uses OpenGL.

On Debian:

```sh
sudo apt-get install build-essential python3-dev libsdl2-dev libgl1-mesa-dev python3-pil
make explore
```

The first launch builds the native libraries in `pocket/build/graphics/`.
Later launches reuse the build. Close the window to quit.

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
