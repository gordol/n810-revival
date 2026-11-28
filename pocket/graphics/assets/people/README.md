# Market people

The clothed mesh, skin, hair, eyes, shoes, rig and walk are derived from
[Relaxed walk – Sam](https://www.innerscene.com/tools/library/3d-parts/relaxed-walk-sam-3d-person-animated-732f1206)
and [Relaxed walk – Maya](https://www.innerscene.com/tools/library/3d-parts/relaxed-walk-maya-3d-person-animated-2c6669a2).
Innerscene credits MakeHuman/MPFB and releases these models and walks under
[CC0](https://creativecommons.org/publicdomain/zero/1.0/).
Sam source GLB SHA-256: fbf6558ff408b6c5d12c82a5aaa506e07ec796f963a9ac1d4b9c88a39b0fd429.

Maya source GLB SHA-256: 3c22e60a599526d264f7cbb744e5bc1f6b1e93a79daade322942c49e7aac6ab3.

The eyewear comes from spamrakuen's CC0 Sagerfrog's Glasses 01 and TBM
Glasses Frames 01. The bake fits the two frames to the animated eyes and stores
them inside the character files. Download the CC0 archive as
`glasses01_cc0.zip` for the packaged build. [MakeHuman Glasses 01 pack](https://static.makehumancommunity.org/assets/assetpacks/glasses01.html)

Rebuild from the repository root with Blender 4.3, NumPy and Pillow:

```sh
blender -b --python-exit-code 1 -P pocket/tools/bake_market_person.py -- sam.glb pocket/graphics/assets/people/sam.zlib glasses01_cc0.zip
blender -b --python-exit-code 1 -P pocket/tools/bake_market_person.py -- maya.glb pocket/graphics/assets/people/maya.zlib glasses01_cc0.zip
```

The bake removes the handheld accessory, simplifies the mesh, atlases the
materials, and samples the rig for a looping stride, two asymmetrical standing poses, a
one-handed toss and a two-handed catch. Pocket solves each leg to a moving shoe contact and shifts the pelvis over
the supporting leg. The shoe rolls from heel contact to toe-off. Sam walks
with a slightly shorter swing on the right. The bake checks forearm and hand triangles against the
torso and trouser cloth at each stride key and between keys. Each pose is
based at the lowest point of its shoes.
The renderer interpolates adjacent poses on the GPU. Scene coordinates use
metres with +Y up and +Z forward.

Seattle shoppers keep a stable appearance throughout their visit. Either base
mesh can wear all 12 top styles, six trouser designs and six shoe designs.
Each garment draws independently from 20 dyes, giving 240 shirts, 120 pairs
of trousers and 120 pairs of shoes. These variations reuse the baked meshes
and material atlas. Head looks include the original cut, a fitted cap, curls,
a bun, loose long hair, a close crop, a single braid, pigtails and twin braids.
The seed also selects hair color, complexion, height, frame width and waist
shape. Skin and clothing share the same mass, abdomen, bust and hip adjustments.
Shoppers can also wear glasses, a chain, a pendant or a watch. Set `POCKET_CITY_SEED` before launch to vary the crowd.

The renderer reads the hand grip and crown from mesh vertices in each pose
to position carried bags, bouquets, caps and hair. Accessories interpolate
with the same pose pair as the mesh.
