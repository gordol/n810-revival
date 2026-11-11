/* SPDX-License-Identifier: MIT */
#ifndef MBX_VGP_BATCH_H
#define MBX_VGP_BATCH_H
#include "mbx_packets.h"
/* Original normal-position batch encoder, not yet device validated.
 * Caller owns packed vec4 positions, row-major mat4, and RGBA constant color.
 * The matrix/program are uploaded once per batch, never once per vertex.
 * No allocation, GPU access, CPU transform, or host result readback occurs.
 */
struct mbx_vgp_position { unsigned xyzw[8]; };
#define MBX_VGP_BATCH_FIXED_COMMANDS 169U
#define MBX_VGP_BATCH_TRIANGLE_COMMANDS 29U
int mbx_encode_vgp_batch(const struct mbx_vgp_position *positions,unsigned triangles,
 const unsigned matrix[16],const unsigned rgba[4],struct mbx_command *commands,
 unsigned capacity,unsigned *written);
#endif
