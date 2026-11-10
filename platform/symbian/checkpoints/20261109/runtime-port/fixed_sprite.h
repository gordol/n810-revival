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
/* Logical caller clip, before any deferred sprite setup. */
int sg_sprite_outer_clip(int *clip);
void sg_sprite_batch_mode(int enabled);
/* Same ordered draws with shared setup; boxes are x,y,width,height. */
int sg_sprite_draw_regions(const struct sg_sprite *,const int *boxes,unsigned count);
unsigned sg_mask_texture(unsigned source,unsigned mask,unsigned flags);
struct sg_mask_source { unsigned long long lifetime,generation; unsigned name,width,height,tracked; };
/* Borrowed hit only; zero retains the caller's flush-before-create path. */
unsigned sg_mask_texture_try_cached(const struct sg_mask_source *,const struct sg_mask_source *,unsigned flags);
unsigned sg_mask_texture_cached(const struct sg_mask_source *,const struct sg_mask_source *,unsigned flags,int *borrowed);
void sg_mask_source_retire(unsigned long long lifetime);
void sg_mask_cache_close(void);
#ifdef __cplusplus
}
#endif
#endif
