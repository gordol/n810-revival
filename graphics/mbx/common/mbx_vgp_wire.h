/* SPDX-License-Identifier: MIT */
#ifndef MBX_VGP_WIRE_H
#define MBX_VGP_WIRE_H
#include "mbx_vgp_draw.h"
#define MBX_VGP_WIRE_MAGIC 0x3156474dU
#define MBX_VGP_WIRE_MAX_BYTES 524288U
#define MBX_VGP_WIRE_MAX_COMMANDS 65536U
/* Little-endian words, no pointers, GPU addresses, or register commands.
 * Current render subset clears opaque RGB to black and depth to one. */
struct mbx_vgp_wire_frame {
 unsigned magic,version,bytes,draws,width,height;
 unsigned clear_color[4],clear_depth,clear_buffers;
};
struct mbx_vgp_wire_draw {
 unsigned bytes,instructions,uniforms,immediates,inputs,vertices,triangles;
 unsigned smooth,cull_mode,viewport[6],reserved;
};
/* Record payload order: program word pairs, uniform vec4s, immediate vec4s,
 * packed input vec4s, triangle indices (u16), zero padding to four bytes. */
unsigned mbx_vgp_wire_draw_bytes(const struct mbx_vgp_draw *);
/* On error, discard the output buffer. No hardware operation occurs here;
 * callers must complete encoding successfully before starting any GPU job. */
int mbx_vgp_wire_encode(const void *data,unsigned bytes,struct mbx_command *,
                        unsigned capacity,unsigned *written);
#endif
