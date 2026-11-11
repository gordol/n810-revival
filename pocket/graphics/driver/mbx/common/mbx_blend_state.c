/* SPDX-License-Identifier: MIT */
#include "mbx_blend_state.h"
/* N95 804a87e0..804a8910: source field bits29..31; destination26..28.
 * SRC_ALPHA_SATURATE has additional side-state and is intentionally rejected. */
int mbx_blend_factors(unsigned source,unsigned destination,unsigned *bits)
{
 unsigned s,d;
 if(!bits)return -22;
 switch(source){
 case 0:s=0;break;case 1:s=1;break;
 case 0x302:s=4;break;case 0x303:s=5;break;
 case 0x304:s=6;break;case 0x305:s=7;break;
 case 0x306:s=2;break;case 0x307:s=3;break;
 default:return -22;
 }
 switch(destination){
 case 0:d=0;break;case 1:d=1;break;
 case 0x300:d=2;break;case 0x301:d=3;break;
 case 0x302:d=4;break;case 0x303:d=5;break;
 case 0x304:d=6;break;case 0x305:d=7;break;
 default:return -22;
 }
 *bits=(s<<29)|(d<<26);return 0;
}
