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
