# Explore the overview, window previews, and backgrounds

Pocket has three desktops, an overview of their layouts, and larger previews for selecting open windows. Animated backgrounds share the terminal cell renderer with those windows. This tour opens local applications, distributes them across desktops, selects a window from its preview, and changes the background.

<video controls playsinline preload="none" poster="../../assets/demos/pocket-overview-effects-20261106-poster.png" aria-label="Pocket desktop overview, window previews, Matrix, rain, snow, leaves, flowers, and Flux"><source src="../../assets/demos/pocket-overview-effects-20261106.mp4" type="video/mp4"><track kind="captions" src="../../assets/demos/pocket-overview-effects-20261106.vtt" srclang="en" label="English actions">[Watch the recording](../../assets/demos/pocket-overview-effects-20261106.mp4).</video>

*91-second laptop recording made on 6 November 2026 in a fresh local session, with service attachment disabled. It uses the portable renderer and captures terminal output at ten frames per second with elapsed time preserved. These are laptop interaction and appearance demonstrations.*

## Read the overview

At **0:20**, the upper row shows a miniature of each desktop. Calendar lives on desktop 2; Connections and Settings live on desktop 1. Below those miniatures, larger previews show the open windows and their contents. The selected preview has a highlighted border. In this checkpoint, some Settings icons appear as question marks in the miniature. The larger application window renders its icons separately; improving miniature fidelity is recorded in the [roadmap](../roadmap.md).

At **0:27**, Tab moves the selection to Calendar. Enter activates it and switches to desktop 2. That connects the overview to a practical task: find an open application, inspect its preview, and return to its desktop.

At **1:24**, the overview opens again over Flux. The windows and their desktop assignments have survived the background changes.

## Follow the controls

From the `pocket` directory, start the desktop:

```sh
make
```

1. Press **Ctrl-]**, then **comma**, to open the application menu. Find Calendar and press Enter.
2. Press **Ctrl-]**, then **@** (Shift-2 on the keyboard used in this recording), to send Calendar to desktop 2. The desktop stays in window-manager mode.
3. Press **comma** to reopen the menu, find Settings, and press Enter. Opening the application returns input to it.
4. Press **Ctrl-]**, then **d**, to open the overview. Use **Tab** to select a preview and **Enter** to activate its window.
5. Press **Ctrl-]**, then **3**, to switch to desktop 3. While in window-manager mode, **b** toggles the background and **e** advances to the next effect.
6. Press **d** to inspect the overview again. Press **q** while in window-manager mode to quit.

Ctrl-] switches between application input and window-manager commands. The [first window-controls tour](laptop-tour.md) demonstrates moving, resizing, maximizing, and focus changes in more detail.

## Follow the background changes

| Time | Background or action | What to look for |
|---|---|---|
| 0:00 | Matrix | Columns of changing terminal glyphs behind the windows. |
| 0:41 | Background off | The recorded toggle leaves visible background glyphs; clearing needs a follow-up fix. |
| 0:45 | Matrix restored | The second toggle resumes the sequence before changing effects. |
| 0:50 | Rain | Slanted rain marks move through the scene. |
| 0:56 | Snow | Snow particles replace the rain pattern. |
| 1:02 | Leaves | Colored leaf particles move across the desktop. |
| 1:08 | Flowers | Flower glyphs replace the leaves. |
| 1:14 | Flux | A changing colored attractor forms curves and trails. |
| 1:24 | Overview over Flux | Window previews appear over the current background. |

Flux plots repeated steps of a Clifford attractor: a pair of equations that feeds each computed point into the next iteration. Density controls how many points contribute to the image; glow and trails influence how those points are drawn. The [Flux implementation](https://github.com/gordol/n810-revival/blob/main/pocket/shell/flux.py) contains the calculation and drawing stages. The [effect catalogue](https://github.com/gordol/n810-revival/blob/main/pocket/shell/effects.py) supplies the background choices, and the [overview layout code](https://github.com/gordol/n810-revival/blob/main/pocket/shell/overview.py) places the window previews.

The [rendering explanation](../explanation/rendering.md) follows application cells through composition and terminal output. The [CPU investigation](../posts/2026-10-18-cpu-acceleration.md) includes the terrain and Room studies, and the [water entry](../posts/2026-10-20-water-and-idle.md) shows a physical N810 capture. Those pages give the workload and measurement context for the more expensive scenes.
