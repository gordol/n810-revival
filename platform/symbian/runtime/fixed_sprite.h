/* SPDX-License-Identifier: MIT */
#ifndef SYMBIAN_FIXED_SPRITE_H
#define SYMBIAN_FIXED_SPRITE_H
struct sg_sprite {unsigned texture;float projection[16],model[16],color[4],xyuv[16];};
/* Current compatibility GL context; caller retains target, blend and clipping.
 * No shader compilation, CPU sampling, rasterization or pixel readback here.
 * color uses normalized RGBA; texture0 means an untextured brush rectangle. */
#ifdef __cplusplus
extern "C" {
#endif
int sg_sprite_draw(const struct sg_sprite *);
int sg_sprite_batch_flush(void);
int sg_sprite_batch_active(void);
int sg_sprite_batch_pending(void);
int sg_mask_batch_prepare(void);
/* Logical caller clip, before any deferred sprite setup. */
int sg_sprite_outer_clip(int *clip);
void sg_sprite_batch_mode(int enabled);
/* Same ordered draws with shared setup; boxes are x,y,width,height. */
int sg_sprite_draw_regions(const struct sg_sprite *,const int *boxes,unsigned count);
struct sg_mask_source { unsigned long long lifetime,generation; unsigned name,width,height,tracked; };
/* Same affine sprite and clipping callback; large masks stream bounded tiles. */
int sg_mask_sprite_draw(const struct sg_sprite *,const struct sg_mask_source *,const struct sg_mask_source *,unsigned flags,
 int (*draw)(const struct sg_sprite *,void *),void *opaque);
void sg_mask_source_retire(unsigned long long lifetime);
void sg_mask_cache_close(void);
#ifdef __cplusplus
}
#endif
#endif
