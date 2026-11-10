/* SPDX-License-Identifier: MIT */
#ifndef MBX_SEPARATE_BLEND_H
#define MBX_SEPARATE_BLEND_H
/* Private userspace annotation, NEVER sent to the kernel. Only valid for
 * depth-disabled RGB SRC_ALPHA/INV_SRC_ALPHA, alpha ONE/ONE, both ADD. */
#define MBX_ALPHA_ADDITIVE_ANNOTATION 256U
#define MBX_ALPHA_OVER_ANNOTATION 8192U
#define MBX_PREMULTIPLY_COPY_FLAG 16384U
#define MBX_ALPHA_COPY_ANNOTATION 32768U
/* Creates two immutable command replays; no pixels, shader math or GPU access.
 * Both outputs NULL selects validation/count only.
 * Source and outputs must not overlap. Failure leaves outputs/count unchanged.
 * GPU/kernel validation remains mandatory before executing either output. */
int mbx_split_separate_blend(const void *source,unsigned bytes,
 void *rgb,void *alpha,unsigned capacity,unsigned *separate_draws);
#endif
