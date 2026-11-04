# Native Reticulum backend

Pocket can run its existing Reticulum service bridge on the pinned microReticulum
core inside the existing radio management process. The Unix owner API, service grants, subscriptions and saved identity stay
the same. Standard RNode KISS owns the selected serial, Bluetooth SPP or HTIT
radio endpoint. Native microLXMF handles signed messages, receipts and stamps
through the same stack and radio. The worker uses the existing framework owner
loop in a thread; it does not start a Python RNS/LXMF process. Explicit stop,
stamp cancellation and reconnect are supported. BLE, raw KISS and transport-router
configurations remain desktop-only when they require the stock Python backend.
Nokia releases use microReticulum and microLXMF; a missing native library or an
unsupported connection is an error, not a Python fallback.

## Build and select

Requires Python 3, Git, CMake 3.15+, a C++17 compiler and bzip2 development headers.
Build dependencies are pinned in `dependencies.lock` and checked outside the
repository. On a desktop:

```
python3 shell/native/reticulum/build.py /tmp/pocket-native --install
make n810
```

The launcher selects the installed native library for supported radio sessions.
On a desktop, set `POCKET_RNS_LIBRARY=stock` to use stock Python RNS/LXMF, or set
it to an explicit library path for a separate test. A missing explicitly
requested library is an error. Nokia releases reject the `stock` override.
ABI 2 is checked before initializing a stack.

For Nokia, cross-compile for ARMv6 soft-float against Debian bookworm or an older
compatible libc. `Dockerfile` supplies that toolchain and an ARM bzip2 library.
Use `build.py --arm --bzip2-library PATH` inside that environment. Pass the tested
build directory, including its `provenance.json`, to
`tools/package_nokia.py --native-reticulum DIRECTORY`. Packaging checks the
library digest, target, ABI and source digests. Retain the previous release until
cold startup and radio acceptance pass on the device.

## Verify

With stock RNS 1.5.7, LXMF 1.2.1 and MessagePack installed:

```
POCKET_TEST_NATIVE_ROLE=a python3 tests/integration/service_mesh.py
POCKET_TEST_NATIVE_ROLE=b python3 tests/integration/service_mesh.py
python3 tests/integration/native_session.py
python3 -m unittest discover -s tests -p test_native_radio.py
```

These exercise encrypted calls through a stock RNS relay, large request/response
resources, pushed subscriptions, independent grants and revocation, and signed
LXMF conversations with delivery receipts, compressed resources and
recipient-required stamps. Stock LXMF verifies saved native message files.
The session test checks reconnect and stamp cancellation without importing Python
RNS or LXMF. The radio tests use pseudo-terminals;
physical radio and whole-system cold-start acceptance are separate requirements.

The C ABI caps owner payloads at 32 KiB, concurrent links at 64 and retained
outgoing resources at 128. Compressed resources have bounded decompression.
Routing and public service discovery are disabled by default. There is no custom
cryptography or Heltec firmware change.

External execution reuses this ABI and the existing service owner. See the
[executor contract](../../../docs/external-node.md) for Auto selection, bounded
leases, binary transport and host acceptance commands. Host acceptance does not
mean a provisioning-only board supports application offload.
