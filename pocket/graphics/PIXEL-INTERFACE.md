# Shared graphical frontend boundary

`graphics.full.Platform(font,renderer_library,display).run(shell_argv)` runs the
complete existing desktop model. `shell.desktop.main(platform=None,argv=None)`
keeps the terminal entry unchanged when no platform is supplied. With a platform,
it injects geometry, input events, structured panel text, native composition
consumption, presentation, selector wait bounds and cleanup. It creates no desktop
PTY and emits no desktop ANSI. Registry/lifecycle ownership stays with shell.

Display contract: events() yields pointer/key/quit/redraw, focus or cancel-input,
and resize events. Resize accepts columns/rows or width/height in content pixels.
The Mac adapter provides dynamic(True), size(), set_canvas(pixel_width,pixel_height)
and present(buffer). Actual model grids change on resize. The shared standalone
Window wrapper also accepts native kind5(column,row); Mac uses its own kind8
pixel-size event adapter. Platform adapters retain fullscreen/window/input duties.

`mbx.Renderer.consume_composed(changed,computed)` consumes each existing native
Host batch before another flush. Host uses observe_composition and serialize=False.
C pocket_mbx_stage_region maps model indices through its viewport origin into the
physical canvas. Structured panel Unicode runs go through pocket_mbx_text. No
Python glyph/pixel traversal. finish() rasterizes staged damage. resize(cols,rows)
changes the pixel buffer and calls pocket_mbx_resize; default100x30, max512x256.

The normal registry's Surface Room factory is replaced only in graphical mode by
PixelRoom. It keeps the app's camera/actions/lifecycle and renders native geometry,
without a scene cell layer. Existing other apps retain their own semantic view
implementations; full-registry integration is not universal3D acceleration.

Native room_pixels.c shares the current GL context. pocket_room_pixels uses packed
RGB565 output; pocket_room_pixels_into adds stride in pixels and capacity in bytes
before tile_limit for direct canvas output. Bounds are checked before drawing.
Rendering remains tiled at400x400. pocket_room_set_eye_height accepts finite0..20000
world units, default340, and preserves state on rejection.

pixel_compositor.Compositor consumes render_image() results in window order.
pocket_pixel_canvas_size sets the current native destination dimensions (up to
4096x4096); image insertion marks coverage, then cached UI/shadow layers replay
only over replaced regions. Launcher and outline layers follow windows. Layers
cache RGB565 plus alpha8; text/chrome remain opaque. This composition is CPU C.
The normal presenter borrows mutable frame storage synchronously; no full-frame
bytes conversion is needed. This is not DMA-BUF or framebuffer zero-copy.

The local fused GPU-alpha candidate uses64x64 RGBA textures, nearest sampling and
source-over before Room's final readback. pocket_room_gpu_layers borrows up to32
layer handles; clear with count zero before freeing them. Both candidate GPU entry
points explicitly reject Nokia MBX until mixed3D/2D state is admitted by its driver.
The programmable GPU path now implements exact RGB565 arithmetic and passes all256
alpha8 values. POCKET_GPU_COMPOSE=1 enables eligible Room/upper-window compositions
locally, including cached shadows; menus/drag retain C composition. Default stays
C because the measured local workload was faster on C. MBX cannot run this fragment
program; its fixed-function path remains guarded pending physical validation.

`Desktop.from_host` remains a small rendering-only attachment; the complete GUI
uses full.Platform. `graphics/launch.py` remains an isolated fixture. `make gui`
launches the full desktop through the repository SDL/OpenGL adapter; `make tui` remains terminal.
All current full-desktop evidence is local. No Nokia access or deployment occurred.

### Shared native GL target

`native/pixel_target.h` defines the owner-thread completion and readback boundary
for Room and GPU cells. Applications draw with standard GL between `begin` and
`end`. The frontend owns the context; the presenter receives top-down RGB565
pixels and handles display transfer. The target borrows the current context,
rejects nesting, checks output spans, and restores framebuffer and pixel-pack
state. Every successful `begin` requires `end`, including error paths.

The default `POCKET_GL_TARGET=legacy` completes OSMesa rendering and copies rows
from its client buffer. `POCKET_GL_TARGET=direct` reads the unchanged default
framebuffer directly into the caller's strided output using
`GL_MESA_pack_invert`. This removes the separate completion and intermediate row
copy. GL readback still synchronizes and copies internally. The tile limit
remains 400x400; larger views use the existing tiling.

The direct path keeps the default framebuffer's orientation. An earlier extra
FBO changed Mesa's viewport orientation and failed hardware Room parity. The
accepted correction removes that FBO. GPU-resident surface reuse remains a
separate driver capability.

Build the renderer with the matching Mesa headers and library, then run the
software-reference comparison from `pocket/`:

```sh
python3 graphics/test_target.py --build build/graphics-nokia \
  --mesa-include /path/to/mesa/include --mesa-library /path/to/libOSMesa.so.8 \
  --cc 'arm-linux-gnueabi-gcc --sysroot=/path/to/sysroot -mcpu=arm1136jf-s -mfloat-abi=soft' \
  --runner 'qemu-arm -cpu arm1136 -L /path/to/sysroot'
```

The reference runner forces softpipe. It compares 177,313 pixels across cells,
Room and tiled Room, checks padding and guards, restores hostile pack state,
and verifies that direct readback leaves the 320,000-byte OSMesa client buffer
untouched. See [the regression guide](REGRESSION.md) for the hardware procedure.

A controlled Nokia comparison on 8 November 2026 matched all 177,313 pixels in
both capture and timing phases. The client-buffer sentinel and legacy capture
comparisons passed. Each mode used 80 measured iterations after ten warmups,
with identical geometry, lighting, format, Mesa library and kernel module.

| Offscreen workload | Legacy iterations/s | Direct iterations/s | CPU ms/iteration, legacy → direct |
| --- | ---: | ---: | ---: |
| 320x200 Room | 31.43 | 36.56 | 22.29 → 18.95 |
| 417x257 tiled Room | 16.59 | 18.84 | 43.52 → 36.56 |
| 64x48 cell pattern, final case | 20.71 | 22.49 | 35.46 → 31.41 |

These are offscreen measurements with state-check overhead. Whole-desktop FPS
and display transfers require a separate frontend measurement. All measured
cases had zero major faults. The capture and timing phases completed 910 GPU
jobs with normal cleanup. Legacy remains the default while combined frontend
acceptance proceeds.
