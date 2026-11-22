# Bundled source

Pocket carries several earlier components under this directory because its
current shell imports them. Their old repositories and engineering records are
not part of this snapshot.

| Path | What is here |
|---|---|
| `packet-console/` | APRS parsing, maps, station and message models, and service code used by Pocket's retained apps and owner services. Some older development entry points remain alongside the modules. |
| `apps/domains/` | Library, MeshCore, reader, Reticulum, and workbench app domains. |
| `map-library-resources/` | Resource mirror used by the registered Map Library module. Its internal `explorations/` path is inherited from that module; it is not a separate project at the repository root. |
| `terminal/` | Bundled terminal dependencies and their licenses. |
| `native/`, `fonts/`, `console-icons/` | Native support and UI assets. |

The shell opens views over shared services; a view does not own the radio or
Bluetooth connection. See [service behavior](../../docs/connections.md) for
the connection path.

## Cells

The Cells app uses the original world model and character renderer from
[kborer/cells](https://github.com/kborer/cells/tree/effccb8141f3951d240ec81d153e45d2b8fb9088),
revision `effccb8141f3951d240ec81d153e45d2b8fb9088`. The seven Python
modules in `terminal_cells/` are unmodified. Their Zero-Clause BSD license
is included in [terminal_cells/LICENSE](terminal_cells/LICENSE).
Pocket owns the clock, input, retained terminal cells and RGB565 presentation.
