/* SPDX-License-Identifier: MIT */
#ifndef MBX_VGP_WIRE_H
#define MBX_VGP_WIRE_H
#include "mbx_vgp_draw.h"
#define MBX_VGP_WIRE_MAGIC 0x3156474dU
#define MBX_VGP_WIRE_MAX_DRAWS 256U
/* CPU wire includes immutable textures plus command metadata. GPU resource
 * and command limits are separate and remain unchanged. */
#define MBX_VGP_WIRE_MAX_BYTES 1048576U
#define MBX_VGP_WIRE_MAX_COMMANDS 65536U
#define MBX_VGP_UPDATE_MAGIC 0x3154474dU
#define MBX_VGP_UPDATE_MAX_BYTES (32U+MBX_VGP_WIRE_MAX_DRAWS*(24U+83U*16U))
/* Updates refer to the exclusive file's last fully validated template.
 * Payload: six viewport words then uniform_words for each draw, in order.
 * No addresses, register offsets, shader code, indices or attribute data. */
struct mbx_vgp_wire_update {
 unsigned magic,version,bytes,draws,generation,reserved[3];
};
struct mbx_vgp_shader_cache;
int mbx_vgp_wire_encode_cached(const void *,unsigned,struct mbx_command *,unsigned,unsigned *,struct mbx_vgp_shader_cache *);
/* One validated command template, bound to its exclusive output-buffer owner.
 * Snapshot storage is caller-owned. Larger frames fall back to full encoding.
 * Callers must invalidate bytes before independently modifying output commands.
 * Legacy capture accepts only self-contained clear frames in versions1..6;
 * newer retained-image dependencies use the explicit prepared-object API. */
struct mbx_vgp_wire_replay_record {
 unsigned wire_offset,bytes,uniform_offset,uniform_words;
 unsigned uniform_command,viewport_command,scissor_words;
};
struct mbx_vgp_wire_replay_cache {
 unsigned char *snapshot;
 unsigned snapshot_capacity,bytes,draws,written;
 struct mbx_command *owner;
 struct mbx_vgp_wire_replay_record record[MBX_VGP_WIRE_MAX_DRAWS];
 unsigned hits,misses;
};
int mbx_vgp_wire_encode_replay(const void *,unsigned,struct mbx_command *,unsigned,unsigned *,
                             struct mbx_vgp_shader_cache *,struct mbx_vgp_wire_replay_cache *);
int mbx_vgp_wire_apply_update(const void *,unsigned,unsigned,struct mbx_command *,unsigned,unsigned *,
                             const struct mbx_vgp_wire_replay_cache *);
/* Little-endian words, no pointers, GPU addresses, or register commands.
 * Current render subset clears opaque RGB to black and depth to one. */
struct mbx_vgp_wire_frame {
 unsigned magic,version,bytes,draws,width,height;
 unsigned clear_color[4],clear_depth,clear_buffers;
};
struct mbx_vgp_wire_draw {
 unsigned bytes,instructions,uniforms,immediates,inputs,vertices,triangles;
 unsigned smooth,cull_mode,viewport[6],reserved; /* v2: bounded blend mode */
};
/* Record payload order: program word pairs, uniform vec4s, immediate vec4s,
 * packed input vec4s, triangle indices (u16), zero padding to four bytes. */
unsigned mbx_vgp_wire_draw_bytes(const struct mbx_vgp_draw *);
/* On error, discard the output buffer. No hardware operation occurs here;
 * callers must complete encoding successfully before starting any GPU job. */
int mbx_vgp_wire_encode(const void *data,unsigned bytes,struct mbx_command *,
                        unsigned capacity,unsigned *written);
/* Zero-initialize once. Trusted owner assigns a nonzero session ID and must
 * not recycle it while old handles exist. Generation never wraps. Storage,
 * commands and this object are exclusively owned and externally serialized.
 * Immutable resources remain in snapshot; this is not GPU residency. */
#define MBX_VGP_PREPARED_SLOTS 4U
struct mbx_vgp_prepared_handle { unsigned session,generation; };
struct mbx_vgp_prepared {
 struct mbx_vgp_wire_replay_cache cache;
 unsigned session,generation,capacity,valid,busy,ready,exports,fault;
};
int mbx_vgp_prepared_create(struct mbx_vgp_prepared *,unsigned,const void *,unsigned,
 struct mbx_command *,unsigned,unsigned char *,unsigned,struct mbx_vgp_shader_cache *,struct mbx_vgp_prepared_handle *);
/* Shared service/Mesa wire dispatch: full typed frame creates a replacement;
 * compact update refers to this session's current generation. Success starts
 * ownership and requires complete after the hardware/verification boundary. */
int mbx_vgp_prepared_dispatch(struct mbx_vgp_prepared *,unsigned,const void *,unsigned,
 struct mbx_command *,unsigned,unsigned char *,unsigned,struct mbx_vgp_shader_cache *,
 struct mbx_vgp_prepared_handle *,unsigned *);
/* bytes==0 replays without any vertex/texture upload or command re-encoding.
 * Otherwise only the validated compact update ABI is accepted. */
int mbx_vgp_prepared_begin(struct mbx_vgp_prepared *,struct mbx_vgp_prepared_handle,const void *,unsigned,unsigned *);
/* Complete only after hardware quiescence and existing verification. A fault
 * pins busy storage until that point; close is not a hardware recovery API. */
int mbx_vgp_prepared_complete(struct mbx_vgp_prepared *,struct mbx_vgp_prepared_handle,int);
int mbx_vgp_prepared_export(struct mbx_vgp_prepared *,struct mbx_vgp_prepared_handle);
int mbx_vgp_prepared_release(struct mbx_vgp_prepared *,struct mbx_vgp_prepared_handle);
int mbx_vgp_prepared_close(struct mbx_vgp_prepared *);
int mbx_vgp_prepared_find(const struct mbx_vgp_prepared *,unsigned,unsigned,unsigned);
/* Trusted recovery path only, after the existing DMA reset-quiescence check.
 * Missing/failed reset or MMU/table evidence leaves ownership unchanged. */
int mbx_vgp_prepared_retire_after_reset(struct mbx_vgp_prepared *,unsigned,unsigned,unsigned);
#endif
