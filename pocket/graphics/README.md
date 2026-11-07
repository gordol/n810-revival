# Pocket graphical frontend

Development checkpoint preserved from ongoing frontend work. This branch is for
continued integration; it is not included in the tested `main` release.
The current build scripts still reference experimental renderer and font inputs
outside this repository (`mbx-driver/display/native` and `outputs/`). A clean
checkout cannot build this draft until those inputs are integrated or replaced
with declared, reproducible dependencies. The source is preserved here so that
work can continue on this branch without relying on an untracked Pocket copy.


- `make tui` runs the existing terminal frontend.
- `make gui` builds and opens the complete graphical desktop through the existing
  platform adapter. On Mac it uses the native OpenGL window adapter, not iTerm or
  the separate ANSI/PTTY compatibility launcher.

The shared entry is `graphics/full.py`. It invokes the actual `shell/desktop.py`
model/event loop with injected input, geometry and presentation hooks. The normal
app registry, Connections, menu, panels, settings, app polling, service ownership,
session handling and cleanup remain in that same implementation. Terminal windows
use their normal application-owned PTYs; the desktop itself does not use a PTY or
serialize/parse an ANSI frame. Service connections remain explicit UI actions.

Native composition batches go directly to the renderer. Panel layout emits
structured text runs and retains the same hit targets. C handles glyph staging
and Mesa/GPU rasterization. There is no Python per-cell rendering loop. Surface
Room's registry entry uses direct native scene pixels, retaining its original632
triangles, camera and lighting. Other apps reuse their existing semantic views;
this does not claim that every app's scene calculations have moved to the GPU.

Resizing changes the actual desktop grid and pixel canvas, rather than stretching
800x480. The Mac adapter reports content dimensions; the shared frontend runs the
normal panel/window layout and resizes retained GPU buffers. Rendering remains in
bounded400x400 tiles. Current native limits are512columns by256rows. Text uses an
8x16 font. Captured font glyphs remain unchanged; explicit chevron and dashed-line
UI glyphs fill known missing characters. Unknown glyphs still fail validation.

Transparent panes, shadows, menus and drag outlines use cached native C pixel
layers above direct Room images. The opt-in programmable GPU-alpha path now matches RGB565 exactly across all256
alpha values, including shadows. It remains off by default because the tested
local workload was faster with C composition. The MBX mixed-state source candidate
is separately compiled/tested; its fixed-function output still needs device proof.
No silent quality reduction or software GPU fallback.

Local evidence is in `../mbx-driver/experiments/gui-native-pixels-20261107/`.
`check_full.py` runs the real24-app registry, menu click, Messages, Settings,
Terminal, direct Room and two grid resizes using isolated state. It verifies no
stdout/desktop ANSI, clean app status and no Room cell layer. Mac GPU and ARM
reference evidence remain separate from physical Nokia proof. This full frontend
has not been installed or tested on the Nokia; Symbian still owns it.

Platform API and native buffer contracts are in `PIXEL-INTERFACE.md`.
`graphics/launch.py` remains the small isolated rendering fixture, not the complete
GUI launcher. `full.py` also accepts explicit font/renderer/display/native-library
paths and a private state directory for other platform adapters or offline tests.
