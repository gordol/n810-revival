/* SPDX-License-Identifier: MIT */
#ifndef MBX_VGP_TRANSFORM_H
#define MBX_VGP_TRANSFORM_H
/* Original bounded transform program. This is an encoder, not proof that the
 * normal geometry transport is connected to Mesa or verified on the N810.
 * Constants: four row-major matrix vectors, one color, two clip-plane vectors.
 * Inputs and results stay on the GPU; no CPU per-vertex matrix operation here.
 */
#define MBX_VGP_TRANSFORM_INSTRUCTIONS 8U
#define MBX_VGP_TRANSFORM_WORDS 16U
int mbx_vgp_transform(unsigned matrix_first,unsigned color,unsigned clip_first,
                      unsigned *words,unsigned capacity);
#endif
