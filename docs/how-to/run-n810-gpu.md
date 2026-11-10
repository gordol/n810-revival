# Run the GPU desktop on the N810

The installed N810 uses a managed framebuffer session. `make gui` starts the
laptop frontend; it does not install the N810 kernel, GPU module or supervisor.

On an already provisioned N810, with no other desktop or graphics test running:

```sh
sudo /usr/local/sbin/n810-pocket-console run
```

The supervisor selects the release at `/usr/local/lib/n810-graphics/current`,
checks its files and kernel compatibility, loads the GPU service and starts
Pocket. On exit it restores the previous console and releases the GPU service.

Check the saved selection without starting the desktop:

```sh
cat /usr/local/lib/n810-pocket/renderer
sudo /usr/local/sbin/n810-pocket-console status
```

`gpu` selects the pixel desktop. The console init service and Pocket boot hook
must invoke the same managed launcher for automatic startup. The renderer
selection has been checked on the physical N810; the protected boot hook still
needs inspection under the shared device reservation. No reboot test has been run.

Symbian runtime sources are included, but a supported Pocket launch handoff is
not installed yet. Do not start a diagnostic harness alongside the GPU desktop:
both would attempt to own rendering and presentation resources.
