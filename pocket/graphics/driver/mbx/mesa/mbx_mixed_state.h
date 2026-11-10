/* SPDX-License-Identifier: MIT */
#ifndef MBX_MIXED_STATE_H
#define MBX_MIXED_STATE_H
#include <string.h>
static inline int mbx_mixed_requested(const char *value){return value&&!strcmp(value,"1");}
static inline int mbx_mixed_depth(int mixed,unsigned enabled,unsigned write,unsigned func){
 if(enabled>1||write>1||func>7)return 0;
 return !enabled||(mixed&&write&&func==1);
}
/* A color-only target never needs depth allocation. A target with depth must
 * initialize both attachments; no partial depth preservation is admitted. */
static inline int mbx_mixed_clear(unsigned buffers,unsigned color,unsigned depth,double value,int scissor,int has_depth){
 return !scissor&&(has_depth?(buffers==(color|depth)&&value==1.0):buffers==color);
}
#endif
