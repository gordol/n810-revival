/* SPDX-License-Identifier: MIT
 * Bounded layout derived from the N95 surface register trace 8049f680..f898.
 * Hardware execution is a separate acceptance gate. No addresses from clients.
 */
#ifndef MBX_DESKTOP_LAYOUT_H
#define MBX_DESKTOP_LAYOUT_H
#define MBX_TA_STATE_BYTES 16384U
#define MBX_TA_STATE_OFFSET 16384U
#define MBX_TA_SAVE_A_OFFSET 32768U
#define MBX_TA_SAVE_B_OFFSET 36864U
#define MBX_TA_RETIRE_OFFSET 40960U
#define MBX_TA_GUARD_OFFSET 45056U
#define MBX_TA_BYTES 49152U
#define MBX_TA_STATE_VA 0xd0000U
#define MBX_TA_SAVE_A_VA 0xe0000U
#define MBX_TA_SAVE_B_VA 0xe4000U
#define MBX_TA_RETIRE_VA 0xe8000U
_Static_assert(MBX_TA_STATE_VA+MBX_TA_STATE_BYTES<=MBX_TA_SAVE_A_VA,"tile state overlaps context");
_Static_assert(MBX_TA_RETIRE_VA+4096<=0x100000U,"context overlaps frame");
/* 801bb5e8 interleaves bits; 801bb6d0..74c takes the maximum of
 * both orientations, multiplies by four and rounds to 32 bytes. */
static unsigned mbx_state_interleave(unsigned x,unsigned y){
 unsigned value=0,i;for(i=0;i<16;++i)value|=((x>>i)&1U)<<(2*i)|((y>>i)&1U)<<(2*i+1);return value;
}
static unsigned mbx_state_bytes(unsigned x,unsigned y){
 unsigned a=mbx_state_interleave(x,y),b=mbx_state_interleave(y,x);return (((a>b?a:b)*4)+31)&~31U;
}
struct mbx_desktop_layout {unsigned tx,ty,words,ta_extent,isp_extent,state_bytes;};
static int mbx_desktop_layout(unsigned width,unsigned height,unsigned enabled,struct mbx_desktop_layout *out){
 unsigned x=25,y=25;
 if(!out||!width||!height)return -22;
 if(width>400||height>400){if(!enabled||width!=800||height!=480)return -22;x=50;y=30;}
 unsigned words=((x+3)/4)*((y+3)/4)*32;
 unsigned state=mbx_state_bytes(((x+3)/4)*4,((y+3)/4)*4);
 if(words*4>0x7000||state>MBX_TA_STATE_BYTES)return -22;
 *out=(struct mbx_desktop_layout){x,y,words,((x-1)<<20)|((y-1)<<10)|0x40000|0xe1,(x-1)|((y-1)<<16),state};
 return 0;
}
#endif
