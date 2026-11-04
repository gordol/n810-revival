# Product versions and reproducible releases

Pocket starts its explicit product version line at 0.1.0 (see VERSION).
This is an initial-development release, not a declaration of a stable 1.0 API.
The desktop and integrated apps currently share one runtime and release version.

Use MAJOR.MINOR.PATCH for the product version. Bump the minor component for
features and the patch component for compatible fixes. At 1.0, incompatible
public interface changes require a major increment. During 0.x, document
incompatible changes and increment the minor component. Owner wire versions and
native ABI versions remain explicit compatibility contracts; product versions
do not replace them. The public integration surface comprises declared app
commands, owner request/snapshot schemas, saved-state schemas and the native C
ABI. Changes require corresponding compatibility tests and migration notes.

Every release also records its full Git commit, immutable payload hashes,
platform, native build provenance and product version. A product version must
not be republished with different contents. Source work after a release needs a
new version before the next release. Historical commit-only releases retain
their existing identities. Current packaging refuses an uncommitted checkout.

Debian packaging is deferred until the ecosystem is more stable. Current Nokia
releases use the existing pinned platform installer, stopped-console guard,
retained previous version and version selector. There is no APT repository or
claim that each application is independently installable today.

Reference snapshots install separately from executable releases. Their manifest
records each file hash and its source release. Private messages, identities,
configuration and RF history are user state and never enter release packages.
