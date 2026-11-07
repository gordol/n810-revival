/* SPDX-License-Identifier: MIT */
#ifndef N810_MBX_VERTEX_PROGRAM_H
#define N810_MBX_VERTEX_PROGRAM_H
#include "mbx_packets.h"
/* Original pass-through program for CPU-transformed Mesa vertices. No vendor
 * program bytes or runtime/container code are incorporated. Wire scheduling
 * and the input/output binding still require Nokia execution validation. */
#define MBX_VERTEX_STARTUP_WORDS 76U
int mbx_encode_vertex_startup(struct mbx_command *commands,unsigned capacity);
#endif
