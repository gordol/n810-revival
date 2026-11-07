/* SPDX-License-Identifier: MIT */
#ifndef MBX_VGP_TOPOLOGY_H
#define MBX_VGP_TOPOLOGY_H
/* Gallium primitive values: triangles=4, quads=7, quad_strip=8.
 * Independent runs retain their own strip boundary. Output uses last-vertex
 * provoking semantics; callers must reject flatshade_first before using it.
 * No vertex math, allocation, or pointer-linked per-primitive objects. */
int mbx_vgp_topology(unsigned primitive, const unsigned *indices,
                     unsigned count, const unsigned *lengths, unsigned runs,
                     unsigned vertices, unsigned short *triangles,
                     unsigned capacity_indices, unsigned *written_indices);
#endif
