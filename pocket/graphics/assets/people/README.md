# Market people

The clothed mesh, skin, hair, eyes, shoes, rig and walk are derived from
[Relaxed walk – Sam](https://www.innerscene.com/tools/library/3d-parts/relaxed-walk-sam-3d-person-animated-732f1206)
and [Relaxed walk – Maya](https://www.innerscene.com/tools/library/3d-parts/relaxed-walk-maya-3d-person-animated-2c6669a2).
Innerscene credits MakeHuman/MPFB and releases these models and walks under
[CC0](https://creativecommons.org/publicdomain/zero/1.0/).
Sam source GLB SHA-256: fbf6558ff408b6c5d12c82a5aaa506e07ec796f963a9ac1d4b9c88a39b0fd429.

Maya source GLB SHA-256: 3c22e60a599526d264f7cbb744e5bc1f6b1e93a79daade322942c49e7aac6ab3.

Rebuild from the repository root with Blender 4.3, NumPy and Pillow:

```sh
blender -b --python-exit-code 1 -P pocket/tools/bake_market_person.py -- sam.glb pocket/graphics/assets/people/sam.zlib
blender -b --python-exit-code 1 -P pocket/tools/bake_market_person.py -- maya.glb pocket/graphics/assets/people/maya.zlib
```

The bake removes the handheld accessory, simplifies the mesh, atlases the
materials, and samples the rig for a looping stride, two asymmetrical standing poses, a
one-handed toss and a two-handed catch. Pocket retains the source leg cycle
and animates the empty arms in time with the opposite foot. Wrist orientation
uses the knuckles so the palms face the thighs at mid-swing. Each pose is based at the lowest point of its shoes.
The renderer interpolates adjacent poses on the GPU. Scene coordinates use
metres with +Y up and +Z forward.
