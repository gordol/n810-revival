# Versions and compatibility

Pocket's desktop and integrated applications share one runtime and product version, recorded in [VERSION](../VERSION). The explicit version series begins at 0.1.0. During the 0.x series, a minor version change can include incompatible interfaces; the release notes describe those changes.

Service protocols and the native C interface carry their own compatibility versions. These cover application commands, owner requests and snapshots, saved-state formats, and the interface between Python and native code. When connecting a service or replacing a native library, check its interface version alongside the product version. The [service transport reference](service-transports.md) describes the connection checks.

A packaged release records its full Git commit, product version, target platform, native build provenance, and file hashes. Those identifiers tie an installation to the source and binaries used to build it. Historical releases identified only by a Git commit retain that identity.

The Nokia installer keeps the previous release and provides a version selector. It installs the desktop and integrated apps together. Reference documentation installs separately, with a manifest recording each file's hash and source release. See [installation](install.md), [Nokia packaging](nokia.md), and the [0.1.0 release notes](releases-0.1.0.md).
