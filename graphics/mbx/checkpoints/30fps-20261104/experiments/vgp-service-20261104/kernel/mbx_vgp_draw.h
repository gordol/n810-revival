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
 unsigned vertex_count,triangle_count,smooth,depth_always,cull_mode;
 unsigned viewport[6]; /* X offset/scale, Y offset/scale, Z offset/scale */
};
/* Caller-owned and externally serialized. Larger programs use the uncached
 * validator. Slots copy program words; no caller pointers survive encoding. */
struct mbx_vgp_shader_cache_entry {
 unsigned instructions,inputs,uniforms,immediates,uniform_color;
 unsigned program[64];
};
struct mbx_vgp_shader_cache {
 struct mbx_vgp_shader_cache_entry entries[4];
 unsigned replace;
};
int mbx_vgp_frame_begin(struct mbx_command *,unsigned capacity,unsigned *written);
int mbx_vgp_draw_encode(const struct mbx_vgp_draw *,struct mbx_command *,unsigned capacity,unsigned *written);
int mbx_vgp_draw_encode_cached(const struct mbx_vgp_draw *,struct mbx_command *,unsigned capacity,unsigned *written,struct mbx_vgp_shader_cache *);
int mbx_vgp_frame_end(struct mbx_command *,unsigned capacity,unsigned *written);
#endif
