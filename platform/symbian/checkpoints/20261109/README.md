# Experimental native Symbian runtime checkpoint

This snapshot preserves the N810 runtime adapters and changes against the
EKA2L1 revision in PROVENANCE.json. Apply eka2l1.patch to that exact upstream
revision and copy upstream-additions over its source tree. runtime-port contains
the separate native frontend and platform adapters. Preserve upstream GPL terms;
EKA2L1-LICENSE accompanies the derived source.

This is source preservation for review, not a reproducible release kit. Toolchain,
dependency acquisition and device launch packaging still need a portable build
recipe. Do not deploy this directory as an installed GPU replacement.

The native path includes ARM execution, E32/import loading, request scheduling,
physical controls, and GPU sprite/mask adapters. N810_SYMBIAN_BATCH_CACHE_HITS
remains an experimental opt-in; its Nokia candidate comparison is outstanding.
The measured Nokia control keeps that option off. BASELINE.md records the test
and its boundaries. measure_host.py measures the corresponding private host
memory sink; the host application has not yet passed N95 initialization.

Users must supply their own compatible firmware, system libraries and application
installers in private storage. No ROMs, DLLs, installers, application captures or
compiled binaries are included. The working graphics stack is a separate
component and this snapshot does not change it.
