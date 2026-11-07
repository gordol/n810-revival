# Running the Pocket desktop in a native Mac window

*7 November 2026. Local Mac results; the graphical frontend is being integrated into the repository.*

Pocket began with cells sent to a terminal. The [console RGB work](2026-10-16-16-bit-console.md) preserved their colors on the N810, and the desktop grew around retained cell layers, input dispatch, windows, and application ownership. A native graphical frontend lets us keep those application interfaces while choosing how their contents reach pixels.

The first Mac experiment drew recorded block cells through OpenGL. It understood spaces and full or half blocks, with a separate color for each half. Its independent pixel check was useful, but it covered only that small vocabulary. Ordinary text, input, application state, and window lifetime needed the rest of the desktop.

## First carry the terminal, then attach to the model

A compatibility launcher ran the real desktop through a pseudo-terminal (PTY), parsed its ANSI output in C, and drew glyphs in a native window. That exercised the existing app catalogue and input handlers. Synchronized-output markers delayed presentation until a coherent terminal update was available.

The direct frontend subsequently attached to the existing `shell.desktop` model. Its platform adapter supplies input, dimensions, presentation, and cleanup. The app registry, launcher, panels, Settings, service ownership, and session lifetime continue through the same desktop implementation. The renderer consumes native composition records directly, and structured text runs draw the panels.

```mermaid
flowchart TB
    apps["Existing apps, registry and desktop state"] --> host["Window layout and retained composition"]
    host --> terminal["Terminal frontend: changed spans and ANSI"]
    terminal --> console["Laptop terminal or N810 Linux console"]
    host --> native["Native frontend: packed batches and text runs"]
    native --> glyphs["C geometry and GPU glyph rendering"]
    room["Surface Room camera and scene"] --> pixels["Direct scene pixels"]
    glyphs --> compose["Window stacking, transparency and shadows"]
    pixels --> compose
    compose --> window["Native platform window"]
```

The normal Terminal application still owns a PTY for its child process. That is a separate relationship from the desktop-to-renderer interface. A terminal inside the graphical desktop remains a terminal application.

The [preserved frontend source](https://github.com/gordol/n810-revival/tree/debbdf2d153371c2fc0d0fc25d14c8f6396f2f56/pocket/graphics) records this boundary. Its [full desktop adapter](https://github.com/gordol/n810-revival/blob/debbdf2d153371c2fc0d0fc25d14c8f6396f2f56/pocket/graphics/full.py) and [pixel interface](https://github.com/gordol/n810-revival/blob/debbdf2d153371c2fc0d0fc25d14c8f6396f2f56/pocket/graphics/PIXEL-INTERFACE.md) are pinned to that development checkpoint. Build-input integration is a subsequent step.

## Let a scene use its actual window resolution

Surface Room retains its camera and input model, while its graphical renderer submits the scene's 632 triangles directly. The scene image occupies the window's pixel area. Controls and other text remain part of the desktop's cell/text interfaces.

![Surface Room rendered directly inside the Pocket desktop.](../assets/screenshots/native-desktop-room-20261107.png)

*Local Mac GPU output captured on 7 November. This is the frontend's rendered image, with Surface Room at pixel resolution inside the shared desktop. It is an intermediate 640 × 400 capture; later tests also exercised changing window sizes.*

The renderer divides drawing into targets up to 400 × 400 pixels. A 640 × 368 Room image therefore requires two tile jobs. Comparing different tile subdivisions exposed depth artifacts with a 16-bit depth buffer. Requesting 24-bit depth removed those artifacts. The local Mac comparison then had zero subdivision differences; the ARM software reference retained a one-channel-step difference in one pixel between its tested subdivisions.

Transparent windows required another pass. An early launcher forced opaque windows while overlapping direct images were unsupported. The subsequent compositor cached native RGB565 images and alpha values for window chrome, shadows, and overlays, replaying them in window order. Moving a window reused its cached layer; closing it released that layer. Tests compared clipped overlap and transparency against an independent pixel calculation.

## Resize the desktop, and check the edges

The early native window scaled an 800 × 480 logical canvas. The later adapter reports actual content dimensions, resizes the desktop grid at the existing 8 × 16 font size, and recreates the relevant render buffers. Existing layout code then repositions panels and windows.

An operating-system resize test exercised 100 × 30, 140 × 50, 80 × 28, and 160 × 54 cells with Room open. It completed 164 frames and 397 Room tile jobs with no form errors. Separate checks compared full pixel output and memory guards, including partial tiles and invalid dimensions.

A border bug left old pixels in presentation margins after resizing. Clearing the complete presentation target before copying the current image fixed the tested cases. A negative control reproduced 200,000 stale margin pixels, showing that the test could detect the defect it was intended to prevent.

The full-desktop acceptance run covered the 24 registered apps, menu actions, Messages, Settings, Terminal, Room, and changing grid dimensions. It recorded 533 frames and 1,036 Room tile jobs without form errors. Those are coverage counts; performance needs matched timing measurements. GPU readbacks, CPU image buffers, and presentation uploads remain in the current path.

The [rendering explanation](../explanation/rendering.md) now places this frontend beside the console path. The [next entry](2026-11-07-surface-room.md) follows the interactive Room experiment, and [GPU effects](2026-11-07-gpu-effects.md) records the later acceleration of existing desktop producers.

<!-- journal-sources:start -->
## Source availability


[Chronological source index](../reference/journal-sources.md#2026-11-07-native-desktop)

The narrative links the preserved graphical frontend development commit. Later Mac platform inputs and acceptance runners are being integrated separately; the captured results describe the tested local build.
<!-- journal-sources:end -->

[Journal](../journal.md)
