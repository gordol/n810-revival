# Shared UI context and input

Pocket already has a small widget framework: `app_widgets`, `controls`, native
navigation, and the retained compositor. Extend those primitives before adding
another app-specific input handler. No mandatory class hierarchy is needed.

## Input defaults

| Action | Nokia console | Keyboard / SSH |
| --- | --- | --- |
| Back one interaction level | Back | Escape |
| Switch to previous window | Home/window switcher | Alt+Tab |
| Menu | Menu | Alt+M |
| Maximize/restore | Fullscreen | Alt+Enter |
| Desktop overview | configurable | Alt+O |
| Zoom in/out in the focused app | top +/- | + / - |
| Window commands | configurable | Ctrl+] |

The Nokia console maps its dedicated keys to F13–F17; Pocket decodes those
sequences without requiring the obsolete `--phone-keys` option. SSH delivers the
client terminal's sequences. `make n810` runs the laptop UI with Nokia services.
An operating system may intercept Alt shortcuts (notably Alt+Tab); Ctrl+] then
Tab cycles windows, Space opens the menu, Z maximizes, and d opens overview.
Double Escape window selection remains a configurable option. It does not skip
an active editor or dialog. No long-press behavior is inferred from key repeat.

Bindings live in `$XDG_CONFIG_HOME/current-world/keys.json` (normally
`~/.config/current-world/keys.json`). Existing version-1 overrides remain valid.
Named global actions now include `desktop.menu`, `windows.switch`,
`windows.maximize`, `desktop.overview`, `view.zoom_in`, and `view.zoom_out`.
Override their arrays of key names to replace the defaults; an empty array
unbinds an action. Hardware keys use `f13` through `f17`. Reload shortcuts from
Settings after editing. Back remains distinct from Tab/Shift+Tab sibling focus.

## Themes and inheritance

Settings → Colors offers the existing palettes plus `light`, `dark`,
`solarized-light`, `solarized-dark`, and `vibe`. The new themes supply body,
panel, toolbar, rail, inset, control, tab, selected, input, heading, accent,
muted, status, and warning materials. The caret reverses body foreground and
background. Map colors retain their geographical/radio meaning.

Start a separate context with `POCKET_THEME=solarized-light make n810` or
`--palette solarized-light`. An explicit command-line choice takes precedence.
New terminal children receive a snapshot of their host's theme in their own
environment; an explicit child environment overrides it. Changing the parent
later does not mutate a running child's environment. Third-party terminal apps
must opt into this variable; Pocket does not rewrite their chosen colors.

`ThemeContext` is an immutable value. `derive()` without overrides returns the
same value. A derived context shares unchanged roles, caches its resolved
read-only role table, and does not modify the parent. `control_ink` accepts
these values as well as preset names. Per-window theme selection UI and theme
file loading are not implemented yet.

## Ownership and work scheduling

Controls emit requested changes to their owner through the existing callbacks.
They do not own a second copy of application state. Sliders at a limit and
single-choice selectors do not publish redundant changes. Text input owns its
editing buffer and exposes text plus semantic spans; ULS and the station filter
use the shared cell-caret presentation. Legacy callers of `draw()` still use its
old presentation and need migration.

Keep contexts immutable, messages small, and mutation inside the owner of a
resource. Do not invent a binary wire format for in-process control events;
use the existing versioned protocols at process/device boundaries. The desktop
already waits on selector readiness and scheduled deadlines. New controls and
themes add no polling or animation timer. Mouse trails are an existing optional
Motion setting; `vibe` is currently a static theme, not an always-running effect.
