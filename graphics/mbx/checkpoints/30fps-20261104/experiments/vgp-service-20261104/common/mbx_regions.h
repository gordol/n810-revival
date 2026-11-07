/* SPDX-License-Identifier: MIT */
#ifndef N810_MBX_REGIONS_H
#define N810_MBX_REGIONS_H
/* Complete an owned region list after TA completion and CPU DMA ownership.
 * Inputs are native-endian words. Caller must perform DMA synchronization.
 * This function never accesses hardware or accepts physical addresses. */
unsigned mbx_morton(unsigned x,unsigned y);
int mbx_finish_regions(unsigned tiles_x,unsigned tiles_y,
                       const unsigned *opb,unsigned opb_words,
                       unsigned parameter_va,unsigned *parameters,unsigned parameter_words,
                       unsigned immutable_words,unsigned *regions,unsigned region_words);
#endif
