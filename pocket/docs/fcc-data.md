# Offline FCC license data

Pocket does not download the FCC database at startup. `make n810` launches the
desktop; it does not fetch data, build a database, or publish one.

On a new install, open **ULS Lookup → Database settings → Download/update FCC
data**. That explicit action downloads the official weekly amateur-license ZIP,
builds an offline SQLite database, and selects it after a successful import.
Progress distinguishes downloading from compilation. Cancel requests cancellation
without replacing the previous database. Opening the app or moving focus onto the
button does not start a download. A failed HTTP request or import stays an error;
it never becomes a successful empty lookup.

The command-line equivalent is:

```sh
make fcc-data
```

This requires Python's standard library, including SQLite, and enough disk space
for the downloaded archive, the final database, and temporary import tables. It
does not require Docker. Building on a laptop and copying the finished database
is preferable when a handheld has limited free storage. Docker is used for the
project's fresh-install tests, not as a dependency of normal lookup or update.

To use an already downloaded official ZIP without network access:

```sh
make fcc-data FCC_ARGS="--archive /path/to/l_amat.zip"
```

The normal user database is `$XDG_DATA_HOME/pocket/uls.sqlite`, defaulting to
`~/.local/share/pocket/uls.sqlite`. The download cache is under
`$XDG_CACHE_HOME/pocket/fcc`, defaulting to `~/.cache/pocket/fcc`. An explicitly
configured `POCKET_ULS_DB` takes precedence; otherwise an existing user database
is preferred over an optional bundled reference snapshot. Updating a bundled
snapshot creates a user copy rather than overwriting the installation.

Updates are explicit. There is no automatic weekly scheduler. The updater uses
HTTP conditional requests and verifies cached archive/database hashes before
skipping an unchanged snapshot. The original snapshot date and import time are
shown separately in lookup results.

## Fields and provenance

The source is the [FCC weekly amateur license archive](https://data.fcc.gov/download/pub/uls/complete/l_amat.zip).
The importer joins license headers, licensee entities, and amateur operator
classes. Schema version 2 retains the licensee's street address, PO Box,
attention line, city/state/postal code, FRN, entity/applicant type, license class,
status, service, FCC identifier, and license dates. EN field positions follow the
[FCC data-file dictionary](https://wireless.fcc.gov/wtbfiles/pa_ddef51.pdf).

The address is the **FCC mailing address**, not a measured RF position. Old local
snapshots that omitted address columns remain readable and explicitly say the
address was not included in that snapshot. An empty field in a new snapshot is
reported as not supplied. Phone/email fields are not imported.

## Distribution

Downloaded ZIPs and SQLite snapshots are local reference data, not source files.
They are excluded from the source release. Reference-data packaging also
excludes FCC data by default. `package_reference_data.py --include-fcc` is an
explicit option for preparing an offline device transfer; ordinary packaging does
not implicitly include the database. No tool uploads a downloaded FCC database.
