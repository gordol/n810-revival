# October CPU and DSP experiments

These source files come from the retained 18 October numerical checkpoint. `vfp/` contains scalar and short-vector arithmetic, ARM1136 probes, context-preservation tests and the benchmark used by the CPU journal entry. `open-c55x/` contains a restricted instruction encoder, FIR and wrapper models, assembler build tools and the experimental relocation patch. `fir_q15.c` is the independent C numerical reference.

The [journal checkpoint guide](../../docs/how-to/test-journal-checkpoints.md#repeat-the-cpu-and-dsp-checks) lists the required compilers, generated fixtures, upstream input pins and test commands. Host model checks, ARM emulation and recorded physical timings each establish different properties.
