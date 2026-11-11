/* SPDX-License-Identifier: MIT */
#ifndef SP_MBX_H
#define SP_MBX_H
#include <stdbool.h>
#include <stdint.h>
void *n810_mbx_fence_create(void);
void *n810_mbx_fence_reference(void *,void *);
bool n810_mbx_fence_finish(void *,uint64_t);
struct softpipe_context;
struct pipe_resource;
void sp_mbx_before_cpu_write(struct softpipe_context *,struct pipe_resource *);
struct pipe_scissor_state;
union pipe_color_union;
bool sp_mbx_clear(struct softpipe_context *, unsigned,
                  const struct pipe_scissor_state *, const union pipe_color_union *, double);
bool sp_mbx_triangle(struct softpipe_context *, const float (*)[4],
                     const float (*)[4], const float (*)[4], const float (*)[4]);
bool sp_mbx_early_cull(struct softpipe_context *);
void sp_mbx_invalidate(struct softpipe_context *);
void sp_mbx_flush(struct softpipe_context *);
void sp_mbx_finish(void);
void sp_mbx_destroy(struct softpipe_context *);
void sp_mbx_present(struct softpipe_context *);
void sp_mbx_checkpoint(struct softpipe_context *);
void sp_mbx_framebuffer_changed(struct softpipe_context *);
const char *sp_mbx_renderer_name(void);
#endif
