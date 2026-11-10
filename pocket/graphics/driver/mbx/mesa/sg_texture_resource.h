/* SPDX-License-Identifier: MIT
 * Candidate GPU resource transport. No MMIO or user-provided GPU addresses.
 * Hardware admission stays restricted until each format passes device proof.
 */
#ifndef SYMBIAN_GPU_TEXTURE_RESOURCE_H
#define SYMBIAN_GPU_TEXTURE_RESOURCE_H
#include <stddef.h>
#include <stdint.h>
#define SG_TEXTURE_MAX_SIDE 1024u
#define SG_TEXTURE_MAX_BYTES (4u*1024u*1024u)
enum sg_texture_format { SG_RGB565=1, SG_RGBA8888=2 };
struct sg_texture_desc {uint32_t side,format,row_bytes,source_bytes;};
/* Packs an unchanged square power-of-two image. RGBA channels stay 8-bit.
 * Source/destination must not overlap. Errors leave destination unchanged. */
int sg_texture_pack(void *,size_t,const void *,const struct sg_texture_desc *);
/* Dimension bits only: format, filtering and addresses are not inferred. */
int sg_texture_dimension_word(uint32_t side,uint32_t *word);
/* Hardware path admission is deliberately separate from packing support. */
int sg_texture_verified(const struct sg_texture_desc *);
#endif
