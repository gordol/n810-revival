# Optional terminal parser dependencies

Only imported when a legacy terminal window is requested. No runtime installation
or network access. All upstream Python source files are unmodified and distributed
here so they remain inspectable and replaceable. The adapter is terminal_host.py.

- pyte 0.8.2, https://github.com/selectel/pyte ; LGPL-3.0, see
  pyte-LICENSE.txt, GPL-3.0.txt and pyte-AUTHORS.txt. Wheel SHA256:
  85db42a35798a5aafa96ac4d8da78b090b2c933248819157fc0e6f78876a0135
  Source archive SHA256:
  5af970e843fa96a97149d64e170c984721f20e52227a2f57f0a54207f08f083f
- wcwidth 0.2.13, https://github.com/jquast/wcwidth ; MIT, see
  wcwidth-LICENSE.txt. Wheel SHA256:
  3da69048e4540d84af32131829ff948f1e022c1c6bdb8d6102117aac784f6859

The Python sources plus upstream LGPL/MIT texts occupy 578211 bytes before adding
AUTHORS and the full GPL text; original wheels total approximately 65 KB compressed.
No tests, packaging metadata, downloaded binaries, or bytecode are vendored.
Python 3.11 is supported by these pinned releases; physical ARM performance of this
PTY path remains to be measured. This is separate from the existing native cell
kernel, which is not changed or required by the PTY prototype.
