# Contributing to N810 Revival

Use a topic branch and open a pull request against `main`. Describe the problem,
the resulting behavior, and how you checked it. The maintainer reviews changes
before integration. The [agent instructions](AGENTS.md) apply to automated work;
the [documentation instructions](docs/AGENTS.md) describe the writing standard.

## Commit messages and versions

Use [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)
for new commits and pull request titles:

```text
fix(launcher): observe the final process state before failing
feat(maps): add area selection for downloads
docs(build): record the verified container build
feat(protocol)!: require the new frame header
```

Use `feat` for features and `fix` for bug fixes. Other supported types are
`build`, `chore`, `ci`, `docs`, `perf`, `refactor`, `revert`, `style`, and `test`.
The scope is optional. Mark incompatible changes with `!` and explain the
migration in a `BREAKING CHANGE:` footer. A breaking-change footer on its own
is also valid Conventional Commits syntax. Preserve that footer in the final
commit message.

The Review workflow checks PR titles (including edits) and every commit introduced
by the PR. Use rebase merges to retain individual commit messages and their
breaking-change footers. GitHub allows rebase merging for this repository.
Historical commits retain their original messages.

We use [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
`pocket/VERSION` is the version for the integrated project; upstream kernel,
Mesa, firmware dependencies and frozen checkpoints keep their own versions.
Source and documentation archives for one release share the same version and
source commit. Git release tags use `vMAJOR.MINOR.PATCH`, with prerelease labels
such as `v0.2.0-rc.1` when appropriate.

The compatibility boundary covers documented app/framework APIs, command-line
options and Make targets, configuration and persisted data formats, and public
IPC and wire protocols. An incompatible change requires migration instructions.
Experimental interfaces must be identified as such in their documentation.

During `0.x` development, increment the minor version for features or breaking
changes and the patch version for compatible fixes. Once `1.0.0` establishes the
stable interface, use major increments for breaking changes, minor increments
for compatible features, and patch increments for compatible fixes. Documentation
and maintenance changes can accompany the next release; their commit type alone
does not determine a version bump. The maintainer reviews the complete change set
before choosing a version. Released tags and archives are immutable.

The existing version is `0.1.0`. Updating a version, creating a tag, and publishing
a release are explicit maintainer actions. Review checks do not publish releases.

## Working checkout

Work from a clone or Git worktree of `gordol/n810-revival`. Pocket is the
`pocket/` directory inside this repository. Start a topic branch here, and run
`make` from that directory for laptop testing. Do not maintain a separate Pocket
repository or copy source between development and publication trees. Use Git
branches or worktrees for parallel work and merge through a pull request.

## Prepare a change

Start with the component README and inspect existing changes. Keep each change
focused enough to review. Include the source, meaningful regression checks,
fixtures, and build inputs needed to reproduce the behavior. Keep dependencies
at documented revisions with checksums where applicable.

Use synthetic inputs for tests involving personal messages, stations, device
identities, or private configuration. Add reviewed screenshots or recordings
when a visible change needs demonstration. Explain whether a result comes from
a host test, VM build, installed package, or physical device.

The repository contains frozen graphics checkpoints. Coordinate imports with
the ongoing GPU work and identify the tested source. Preserve independent work
and active device sessions. Hardware and radio operations require their own
explicit authorization.

## Check the result

Run the relevant commands in [Run the Pocket tests](docs/how-to/validate.md).
The baseline checks are:

```sh
make pocket-smoke
make docs-install
make docs-check
```

The publication checker examines tracked files and requires a reviewed, staged
tree. Review the diff, stage only intended files, then run it. The site build
checks links and renders documentation; inspect affected pages and media too.
Use the component build guides for kernel, graphics, HTIT, and map-data changes.

GUI interaction checks must wait for rendered state and fail if the sequence
does not complete within a bounded timeout. Verify graphics harness changes
with `xvfb-run -a python3 pocket/graphics/check.py --allow-software` on Linux;
a passing Mac GPU run does not cover the CI software renderer.

Before uploading any history, run `python3 tools/check-history.py` locally and
inspect relevant metadata and media. Redacting the latest file alone leaves
earlier copies in history. Keep private recovery copies outside this repository.

## Licenses and attribution

Preserve every applicable upstream notice and license. Identify the origin and
redistribution terms of imported code and assets. Add accurate SPDX notices to
original files once their license is established. An SPDX label identifies terms;
the accompanying license text supplies them.

Contributions to GPL-covered software must provide compatible GPL rights and accurate attribution. GPL permissions already permit compliant commercial redistribution by the maintainer and other recipients.

For contributions to Cat Wormhole-covered material, read [Contributor Agreement 1.0](CONTRIBUTOR-AGREEMENT.md). Provide explicit acceptance for the identified changes before integration when the project needs that additional commercial grant. The agreement preserves contributor ownership and permits the Project Steward to extend and sell accepted contributions. Existing upstream material keeps its own terms; identify it separately.

Use the attribution procedure in [CONTRIBUTORS.md](CONTRIBUTORS.md). A submission, PR checkbox, or sign-off alone grants no additional commercial permissions. Keep signed acceptance records private and record only a non-sensitive reference in the review. Publicly distributed modified binaries under [Cat Wormhole License 0.4](LICENSE.md) must include matching Corresponding Source as specified there.

## Pull request review

Use the PR template to record the behavior, validation, source inputs, visual
evidence, and remaining limitations. Link documentation within the site and code
to the corresponding repository files. Keep sensitive research records local.

Copilot can provide an additional review. The maintainer evaluates its findings
and makes the merge decision. Review changes to workflows, agent instructions,
license declarations, and media-review manifests as carefully as runtime code.

The local checks and policy files are preparation. Live enforcement requires
GitHub rulesets to be enabled and verified. The repository settings
records that activation procedure and the proposed protection for `main`.

## Runtime artifacts

Keep tests and engineering diagnostics in the development source. Guard optional
diagnostic implementation with the explicit `DEVELOPMENT` build feature and
verify the exported release with the implementation modules absent. Default-off
collection alone is not a release boundary. Do not use Python `-O` to remove
required validation, or copy a full checkout to a production runtime.
