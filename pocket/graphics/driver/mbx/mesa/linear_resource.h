/* SPDX-License-Identifier: MIT */
#ifndef MBX_LINEAR_RESOURCE_H
#define MBX_LINEAR_RESOURCE_H
#include <stddef.h>
struct mbx_linear_source {
 const unsigned char *data;size_t bytes,stride;
 unsigned width,height,rgba,opaque,repeat;
};
/* Copies/converts resource bytes and a one-texel addressing border. No
 * resampling, shading or rasterization. Destination must not alias source. */
size_t mbx_linear_size(unsigned width,unsigned height,unsigned *stride_pixels);
int mbx_linear_pack(const struct mbx_linear_source *,void *,size_t);
#endif
