# A laptop tour of the window controls

This one-minute demonstration opens Help and Calendar, moves and resizes a window, maximizes and restores it, switches desktops, and opens Settings. It was recorded on 4 November 2026 from a separate local Pocket session.

<video controls playsinline preload="metadata" poster="../../assets/demos/laptop-window-tour-20261106-poster.png"><source src="../../assets/demos/laptop-window-tour-20261106.mp4" type="video/mp4"></video>

This 54-second recording was made on 6 November 2026 using actual terminal output and scripted keystrokes. It is rendered at ten captured frames per second with a label showing each action. The session used generic local state, detached services, the portable compositor, and disabled animation. The recording demonstrates controls; device performance measurements are in the journal.

## Follow along

From the `pocket` directory, start the desktop:

```sh
make
```

A first session opens Connections. Later launches restore your saved windows.

1. Press **?** to open contextual Help. Press **Tab** to focus Topics, use **Up/Down** to select a topic, and press **Tab** again to read its preview. Up/Down scrolls Reading.
2. Press **Ctrl-]**, then **comma**, to open the application menu. Type **Calendar** to filter it, then press **Enter**.
3. Press **Ctrl-]**, then **m**, to start moving the Calendar window. Use the arrow keys to position it and **Enter** to keep the change. **Escape** cancels a move.
4. While still in window-manager mode, press **r** and use the arrow keys to resize. Press **Enter** to keep the size.
5. Press **Shift-Z** to maximize the window. Press it again to restore the previous size.
6. Press **2** to show desktop 2 and **1** to return to desktop 1.
7. Press **F6** to select the next window and return input to that application. **Shift-F6** selects the previous one.
8. Open the application menu again, find **Settings**, and use **Tab** and the arrows to explore its categories.
9. Press **Ctrl-]**, then **q**, to quit.

The **Ctrl-]** prefix switches input between the application and the window manager. Movement and resize commands operate on the focused window. This keeps ordinary letters available to applications when their input is active. The [keyboard reference](../pocket/navigation.md) covers the shared application controls.

## What to read next

Continue with the [overview and backgrounds tour](overview-and-backgrounds.md) to select windows from previews and see Matrix, weather effects, and Flux in motion.

The [early APRS entry](../posts/2026-10-14-aprs.md) shows the tmux workspace that came first. The [Pocket desktop entry](../posts/2026-10-16-pocket-desktop.md) follows the move to this window model. The [SSH guide](../how-to/ssh.md) explains how a laptop can either display the tablet's terminal session or run Pocket locally and attach to the tablet's services.
