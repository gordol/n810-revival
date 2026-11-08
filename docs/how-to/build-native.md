# Build the local native compositor

Install a C compiler and development headers matching the Python interpreter used to launch Pocket. From the repository root, run:

```sh
make -C pocket native
make -C pocket
```

The build helper places artifacts in the Pocket native cache under `$XDG_CACHE_HOME`, or the user's default cache directory. Source hashes, platform identity, and interpreter identity select the matching build. The launcher can use the portable renderer when compilation is unavailable.

Exercise the same window layout before comparing performance. Record terminal dimensions, backend selection, startup time, and the interaction being measured. The [rendering explanation](../explanation/rendering.md) identifies the stages involved.

Nokia packages use an ARM build matched to the installed runtime. The [Nokia packaging guide](../pocket/nokia.md) describes that separate build path and its required inputs.
