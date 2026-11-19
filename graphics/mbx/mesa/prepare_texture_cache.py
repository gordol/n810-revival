"""Restore the prepared N810 Mesa cache layout in reproducible source builds.

Keep cache capacity and sampling unchanged. Metadata writes must not fault in
unused 16 KiB software texture payload pages on the GPU path. Payloads are
zeroed on their first software sample, as in the pinned working source.
"""
import hashlib
from pathlib import Path
import subprocess

HASHES = {'sp_tex_tile_cache.h': ['095c9bee295a2636a2e5a7e817e35a72347ae56ca2aba6cdf56e962287840e87', 'd0b6087569940e45443c670a66fa3d2f79a1310c98ff55663a328f507447e0a9'], 'sp_tex_tile_cache.c': ['4ee31aade1b4e795e5a8bd14c98ca589b0d1e55822526ee8ae0260f3f8856576', 'd1fee2b8ebb0fb3c280c0a7a6a2e5693bc666b8b0891d2ce5096d52bbb8ccbe4']}


def prepare_texture_cache(directory):
    directory=Path(directory)
    observed={name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in HASHES}
    if all(observed[name]==pair[1] for name,pair in HASHES.items()):return
    if any(observed[name]!=pair[0] for name,pair in HASHES.items()):
        raise ValueError('Unexpected Mesa texture-cache source; refusing an ambiguous patch')
    subprocess.run(['patch','--batch','-p0','-i',str(Path(__file__).with_name('texture-cache-metadata.patch').resolve())],cwd=directory,check=True)
    for name,pair in HASHES.items():
        if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=pair[1]:
            raise ValueError('Texture-cache patch does not match the known working source')
