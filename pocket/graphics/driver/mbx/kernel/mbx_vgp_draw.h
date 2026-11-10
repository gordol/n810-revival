/* SPDX-License-Identifier: MIT */
#ifndef MBX_VGP_DRAW_H
#define MBX_VGP_DRAW_H
#include "mbx_packets.h"
/* A bounded, contiguous raw-input draw. Connectivity expansion is CPU work;
 * transform, normal normalization and lighting stay in the shader program.
 * Caller retains ownership until encoding completes. No MMIO/address inputs. */
struct mbx_vgp_draw {
 const unsigned *program,*uniforms,*immediates,*vertices;
 const unsigned short *indices;
 unsigned instructions,uniform_count,immediate_count,input_count;
 unsigned vertex_count,triangle_count,smooth,depth_always,depth_disabled,cull_mode;
 unsigned blend_mode,texture_enabled,texture_input,texture_128,texture_native32;
 unsigned color_input; /* wire bit17: complete RGBA vector in input1 */
 unsigned texture_modulate; /* explicit wire bit16, RGBA/RGB replacement remains default */
 unsigned texture_page; /* 0: legacy placement; otherwise owned final-eight-page index1..8. */
 unsigned mask_operation; /* internal mask geometry: 0 none, 1 reset, 2 rectangle */
 unsigned texture_arena; /* RGB565 offset in driver-owned guarded arena */
 unsigned texture_window_native; /* layout2 resource version14 */
 unsigned texture_window; /* one-based validated rendered-image slot */
 unsigned texture_linear_width,texture_linear_height,texture_linear_offset; /* validated bordered resource dimensions */
 unsigned viewport[6]; /* X offset/scale, Y offset/scale, Z offset/scale */
};
/* Caller-owned and externally serialized. Larger programs use the uncached
 * validator. Slots copy program words; no caller pointers survive encoding. */
struct mbx_vgp_shader_cache_entry {
 unsigned instructions,inputs,uniforms,immediates,uniform_color,texture_enabled,texture_input,color_input;
 unsigned program[64];
};
struct mbx_vgp_shader_cache {
 struct mbx_vgp_shader_cache_entry entries[4];
 unsigned replace;
};
/* Encoder-owned patch locations; never inferred from packet lengths. */
struct mbx_vgp_draw_patches { unsigned uniform_command,viewport_command; };
int mbx_vgp_draw_encode_patches(const struct mbx_vgp_draw *,struct mbx_command *,unsigned,unsigned *,struct mbx_vgp_shader_cache *,struct mbx_vgp_draw_patches *);
int mbx_vgp_frame_begin(struct mbx_command *,unsigned capacity,unsigned *written);
int mbx_vgp_draw_encode(const struct mbx_vgp_draw *,struct mbx_command *,unsigned capacity,unsigned *written);
int mbx_vgp_draw_encode_cached(const struct mbx_vgp_draw *,struct mbx_command *,unsigned capacity,unsigned *written,struct mbx_vgp_shader_cache *);
int mbx_vgp_frame_end(struct mbx_command *,unsigned capacity,unsigned *written);
#endif
