# Working on N810 Revival

This repository contains Pocket, N810 platform and kernel inputs, HTIT firmware,
frozen graphics checkpoints, and the documentation site. Read the relevant
component README and [CONTRIBUTING.md](CONTRIBUTING.md) before making changes.
Instructions in this file apply throughout the repository. More specific
instructions may add requirements for a subtree.

## Canonical source

This GitHub repository is the working source, including `pocket/`. Use topic
branches and Git worktrees for parallel changes. Do not export a second editable
Pocket copy or import private development history. Preserve ongoing work and
review source diffs when reconciling an older snapshot.

## Scope and coordination

- Inspect the working tree and staged changes first. Preserve unrelated work.
- Carry authorized work through implementation and relevant verification. Ask
  for missing decisions that actually block progress. Reuse explicit permission
  within its stated scope; routine local edits and checks need no renewed approval.
- Treat a request for discussion or review as that scope. Publishing, pushing,
  merging, deployment, and release creation require authorization for that action.
- Follow the Conventional Commits and SemVer policy in CONTRIBUTING.md for new
  commits, PR titles, and version changes. Preserve breaking-change footers when
  squash-merging. Release tags and publication require explicit authorization.
- Use topic branches and pull requests for shared changes. Review the exact staged
  diff before committing. Never infer remote branch protection from local files.
- The publication tree contains frozen checkpoints. Import reviewed snapshots
  with source identities and verification records. Coordinate with the owner of
  ongoing experiments before touching their working tree or active test session.
- When several chats work on the project, name the files and component each owns.
  A handoff records the change, evidence, remaining work, and allowed next actions.
- Treat synced reference material as read-only. Keep personal notes, raw chat
  exports, and private recovery records outside the distribution tree.

## Hardware and external effects

- Host tests, VM builds, device installation, running processes, persistence
  across reboot, and physical or radio observations are separate evidence states.
  State which ones were actually checked.
- Device reboot, flash, module loading, radio transmission, provisioning, and
  other state-changing device operations need explicit authorization covering
  the target and operation. Preserve active services and saved preferences.
- Before any authorized VM or device action, identify the host or VM, transfer
  path, exact operation, and recovery approach. A successful VM build establishes
  a build result; hardware acceptance requires observations on that hardware.
- Quarantined inputs require specific authorization before opening, hashing,
  copying, parsing, extracting, or executing them. Permission for one artifact
  does not extend to another. An explicit stop takes effect immediately.

## Implementation and evidence

- Fix the underlying behavior with the smallest coherent change. Prefer existing
  component interfaces and narrow platform adapters. Keep user-facing controls
  focused on actions and current state; put engineering explanations in Help.
- Closing a view releases its owned resources. Shared acquisition services keep
  serving other views. Preserve saved preferences and distinguish collector
  health from client-directory activity.
- Include necessary source, tests, fixtures, build scripts, configurations,
  dependency revisions and checksums with a documented checkpoint. Review their
  redistribution rights. Identify owner-supplied inputs explicitly.
- Verify fresh-checkout build claims in an isolated checkout using documented
  inputs. A prepared developer environment alone cannot establish reproducibility.
- Report build success, functional equivalence, and byte-for-byte reproduction
  as separate results. Retain exact source and artifact identities for claims.
- Performance reports identify hardware, clocks, workload, dimensions, method,
  sample duration and statistic. Separate startup and paging from steady samples,
  and rendering throughput from display transfers. Compare matched workloads.
- Verify Help instructions through the desktop key dispatcher, including initial
  focus, Tab order, selection, and scrolling. Use the registered application
  factory and its wrappers; a base-class test can miss controls added by the
  actual application. Follow reader walkthroughs in a make-launched desktop.
- Exercise actual UI behavior when it changes. Inspect captures and interactions
  at the target dimensions. A host preview demonstrates host behavior; record
  physical-device acceptance separately. Mark synthetic and reconstructed demos.

## Privacy and licensing

- Inspect text, media, metadata, fixtures, archives, and history for credentials,
  personal callsigns, device identities, messages, and precise personal locations.
  Keep private records local. Use documented fictional fixtures where appropriate.
- Scanner success complements manual review. Review media visually and record
  its SHA-256 in `tools/release-assets.json`; keep the detailed review locally.
- Preserve upstream copyright notices and license terms. Map licenses by
  component and derivation before changing headers or redistribution terms.
- The Cat Wormhole License in LICENSE.md covers the documented original prose.
  Original software grants are recorded in LICENSE-SCOPE.json and
  licenses/ORIGINAL-CODE-GPL.md. Preserve each entry's license and upstream terms.
  Combined-program and asset release review remains separate. Preserve
  upstream terms and require provenance review before extending coverage.
  Thomas Gordon Lowrey IV is the holder for his eligible original material.
- Use SPDX notices when licensing is established. Custom licenses use a
  `LicenseRef-` identifier and an accompanying full text. Source notices and
  offline Help/About notices must agree with the packaged components.
- Keep legal grants and disclaimers precise. Humor belongs in clearly identified
  asides. Changes to contributor commercial rights require express agreement.

- Keep public GIS downloads, map tiles, terrain packs and map caches out of Git.
  Ship their acquisition/build tools and source attribution. Use small fictional
  fixtures for offline builder tests and identify regional integration tests.
  Map UI and terrain tests must also run from a source-only checkout. Use
  `pocket/tests/reference_fixtures.py` for fictional reference packs; keep any
  real-data integration prerequisite explicit.

## Validation and completion

The docsite serves readers using, building, and understanding the project.
Keep repository administration and publication procedures in `maintainers/` or
root contributor files. Put technical progress and measurements in the journal;
keep the homepage focused on the introduction, demonstration, and first steps.
Keep internal audit and review records local.

Use [the validation guide](docs/how-to/validate.md) and the relevant build guide.
Run focused regression checks for changed behavior; run the full relevant build
when changing its inputs. Do not substitute a passing unrelated suite for proof.

- `make pocket-smoke` checks selected desktop behavior on the host.
- `make docs-install` installs pinned documentation dependencies.
- `make docs-check` checks staged publication inputs, journal links, and the
  strict site build. Review and stage only intended files before running it.
- `python3 tools/check-history.py` audits all locally present Git objects before
  publication. Its scope depends on which history is actually present locally.

Before handoff, inspect the diff and report what changed, checks and outcomes,
remaining gaps, and a concrete way to review the result. Keep implementation,
installation, device verification, and publication status explicit.

When a correction reveals a durable project rule, update the relevant contributor
instructions with the concise lesson and verification method. Keep current facts
in their component documentation; keep private conversation records outside the
repository. Check that instructions still match the actual commands and layout.
