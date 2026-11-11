/* SPDX-License-Identifier: MIT */
#ifndef MBX_VGP_STREAM_H
#define MBX_VGP_STREAM_H
#include "mbx_packets.h"
struct mbx_vgp_stream_io {
 void *cookie;
 unsigned (*status)(void *);
 void (*write)(void *,const struct mbx_command *);
 void (*write_barrier)(void *);
 void (*pause)(void *);
 /* Optional ordered writer for one already-reserved credit burst. */
 void (*write_batch)(void *,const struct mbx_command *,unsigned);
 unsigned spin_polls;
 void (*relax)(void *);
};
struct mbx_vgp_stream_result {unsigned written,status_reads,pauses,last_status,spins;};
/* Exclusive producer only. Reserve observed free FIFO capacity once per burst;
 * sideband writes consume a credit conservatively, as in the reference driver.
 * Caller owns completion/quiescence and must retain buffers on any error. */
int mbx_vgp_stream(const struct mbx_vgp_stream_io *,const struct mbx_command *,
                   unsigned count,unsigned polls,struct mbx_vgp_stream_result *);
#endif
