/* SPDX-License-Identifier: MIT
 * Whole-frame vertex submission. No CPU transform, lighting, or rasterization.
 * Context-owned shader cache compares token contents, not recycled pointers.
 */
#include "draw/draw_private.h"
#include "draw/draw_vs.h"
#include "draw/mbx_vgp_shader.h"
#include "draw/mbx_vgp_topology.h"
#include "draw/mbx_vgp_wire.h"
#include "draw/mbx_image_abi.h"
struct mbx_vgp_cached_shader {
 struct mbx_vgp_cached_shader *next;
 struct mbx_vgp_shader program;
 unsigned tokens;
 struct tgsi_token code[];
};
#include "mbx_texture_resident.h"
struct mbx_vgp_queue {
 struct mbx_texture_resident textures;
 unsigned char *texture_compact;
 uint64_t texture_compact_bytes,texture_compact_jobs;
 uint64_t resource_epoch;
 unsigned char data[MBX_VGP_WIRE_MAX_BYTES];
 struct mbx_vgp_cached_shader *shaders;
 bool retain_checked,retain,clear_header_only,fixed_copy;
 unsigned retain_verified,last_draw_bytes;
 uint64_t retained_bytes,copied_bytes;
 bool use_template,template_dirty;
 unsigned template_generation,update_bytes,template_uploads,template_updates;
 uint64_t template_upload_bytes,template_update_bytes;
 struct mbx_vgp_wire_frame template_frame;
 unsigned char *update,*template_snapshot[MBX_VGP_PREPARED_SLOTS];
 unsigned template_snapshot_bytes[MBX_VGP_PREPARED_SLOTS],template_snapshot_capacity[MBX_VGP_PREPARED_SLOTS];
 unsigned template_slot_generation[MBX_VGP_PREPARED_SLOTS],template_next;
};
static bool sp_mbx_vgp_draw(struct draw_context *draw,const struct draw_vertex_info *v,
                           const struct draw_prim_info *prim);
