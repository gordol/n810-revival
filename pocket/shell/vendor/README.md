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
