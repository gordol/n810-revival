/* SPDX-License-Identifier: MIT */
#ifndef SYMBIAN_MBX_CHANNEL_SELECT_H
#define SYMBIAN_MBX_CHANNEL_SELECT_H
#include "mbx_packets.h"
/* Region extension is local-only. Set RGBA bits select source B; clear bits A.
 * Local candidate only. The caller must own distinct input/output allocations,
 * fence both inputs, and validate the complete stream before any submission.
 * No user-supplied GPU addresses, no allocation, no pixel evaluation. */
#define MBX_CHANNEL_SELECT_COMMANDS 112U
int mbx_channel_select_region(unsigned width, unsigned height, unsigned rgba_mask,
 struct mbx_command *out,unsigned capacity,unsigned *written);
int mbx_channel_select64(unsigned rgba_mask, struct mbx_command *out,
                         unsigned capacity, unsigned *written);
#endif
