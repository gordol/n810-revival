/* SPDX-License-Identifier: MIT */
#ifndef MBX_VGP_ISA_H
#define MBX_VGP_ISA_H
struct mbx_vgp_source { unsigned bank,index,swizzle,negative; };
/* Inputs0..15, constants0..127, temporaries0..13. Destination selectors are
 * explicit; output7 is only established for the normal N95 VGP path. */
int mbx_vgp_encode(unsigned opcode,unsigned destination,unsigned mask,
 const struct mbx_vgp_source *sources,unsigned count,unsigned words[2]);
#endif
