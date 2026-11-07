# Source validation

Run the suite as an ordinary user from a clean checkout:

```sh
python3 -m pip install -r requirements-test.txt
POCKET_DATA_ROOT=/path/to/prepared/reference-data python3 -m unittest discover -s tests
```

NumPy and Pillow exercise the desktop DEM and water raster paths. Without them,
those paths fall back in the app but the reference raster checks cannot pass.
These are development dependencies, not an instruction to install them on Nokia.
The console shell retains its portable map path. Optional native/client tests
report skips when their separate dependencies are unavailable.

`POCKET_DATA_ROOT` points at the existing prepared data directory, normally
`data/` in the working checkout. The tests do not download reference data. A clean
source worktree without those ignored assets needs this explicit reference root;
missing data must not be confused with a successful map validation.

For Linux, Python 3.11, `make`, a C/C++ compiler, NumPy and Pillow cover the source
suite used in the November stabilization pass. On Debian bookworm the raster
packages are `python3-numpy` and `python3-pil`. Run the tests as a non-root user:
the Nokia session entry point intentionally refuses root. Network access can be
disabled and source/reference mounts made read-only; test state and builds use
temporary directories. Functional map interaction fixtures allow up to 60 seconds
for a cold reference-data load; their timeout is not a pan/zoom latency target.
Measure UI latency separately with retained map state. No shared Nokia, USB devices or physical radio are needed.

For concurrent development, create a separate committed-source worktree before
running the suite. Record its revision, Python version, reference-data root,
pass/failure/skip totals and log location. Do not include another agent's dirty
native/graphics changes in the result. Source tests, installation verification,
physical rendering, and RF/second-device acceptance are separate evidence.
