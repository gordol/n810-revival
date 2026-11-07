/* SPDX-License-Identifier: MIT
 * Whole-frame vertex submission. No CPU transform, lighting, or rasterization.
 * Context-owned shader cache compares token contents, not recycled pointers.
 */
#include "draw/draw_private.h"
#include "draw/draw_vs.h"
#include "draw/mbx_vgp_shader.h"
#include "draw/mbx_vgp_topology.h"
#include "draw/mbx_vgp_wire.h"
struct mbx_vgp_cached_shader {
 struct mbx_vgp_cached_shader *next;
 struct mbx_vgp_shader program;
 unsigned tokens;
 struct tgsi_token code[];
};
struct mbx_vgp_queue {
 unsigned char data[MBX_VGP_WIRE_MAX_BYTES];
 struct mbx_vgp_cached_shader *shaders;
};
static bool sp_mbx_vgp_draw(struct draw_context *draw,const struct draw_vertex_info *v,
                           const struct draw_prim_info *prim);
