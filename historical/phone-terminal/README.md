# Historical phone terminal bridge

The October bridge presents an SSH/tmux session through an authenticated HTTPS service. `server.cjs` owns authentication and the pseudo-terminal, `workspace.cjs` validates session selection, and `public/` supplies the browser interface. `runtime/package-lock.json` pins xterm.js, node-pty and ws with their transitive dependencies.

The [journal checkpoint guide](../../docs/how-to/test-journal-checkpoints.md#check-the-sidebar-and-phone-terminal) explains the offline tests and service inputs. `setup.py` requires the intended SSH target and control socket and creates local credentials in `.private/`. That directory and `node_modules/` are ignored by Git.
