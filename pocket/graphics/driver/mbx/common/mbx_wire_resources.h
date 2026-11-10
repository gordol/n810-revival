/* SPDX-License-Identifier: MIT
 * Bounded resource table for a future wire-v6 path. No GPU addresses on wire.
 * This parser alone does not enable submission in the existing driver.
 */
#ifndef MBX_WIRE_RESOURCES_H
#define MBX_WIRE_RESOURCES_H
#include "mbx_window_images.h"
#define MBX_WIRE_LINEAR_PAYLOAD (786432U-8192U)
#ifdef __KERNEL__
#include <linux/string.h>
#else
#include <string.h>
#endif
struct mbx_wire_resource { unsigned version,bytes,offset,reserved; };
struct mbx_wire_resources {
 unsigned count,bytes,data_offset,draw_offset;
 struct mbx_wire_resource item[64];
};
static inline unsigned mbx_resource_bytes(unsigned version){return version==3?8192:version==4?32768:version==5?16384:0;}
static inline int mbx_wire_resources_parse(const void *data,unsigned bytes,struct mbx_wire_resources *out){
 const unsigned char *raw=data;unsigned header[12],table[4],i,pad;
 unsigned count=0,total=0,data_offset=48,draw_offset=48,at=0,first_type=0;
 struct mbx_wire_resource legacy={0};
 if(!data||!out||bytes<48)return -22;
 memcpy(header,raw,48);
 if(header[0]!=0x3156474dU||header[2]!=bytes||header[1]<1||(header[1]>6&&header[1]!=9&&header[1]!=10))return -22;
 if(header[1]>=3&&header[1]<=5){
  count=1;total=mbx_resource_bytes(header[1]);if(bytes-48<total)return -22;
  legacy=(struct mbx_wire_resource){header[1],total,0,0};draw_offset=48+total;
 }else if(header[1]>=6){
  if(bytes<64)return -22;memcpy(table,raw+48,16);count=table[0];total=table[1];
  if(!count){if((header[1]!=9&&header[1]!=10)||total||table[2]||table[3])return -22;data_offset=draw_offset=64;}
  else{
   if(count>64||(count>4&&header[1]!=9&&header[1]!=10)||total>MBX_WIRE_LINEAR_PAYLOAD||table[2]||table[3])return -22;
   data_offset=64+16*count;if(bytes<data_offset||bytes-data_offset<total)return -22;
   for(i=0;i<count;++i){
    struct mbx_wire_resource r;unsigned expected,width,height,aligned;
    memcpy(&r,raw+64+16*i,16);if(!i)first_type=r.version;
    if(first_type==7||first_type==10){if((i==0&&r.version!=first_type)||(i>0&&r.version!=8))return -22;}
    else if(((r.version==8||r.version==12||r.version==13||r.version==14))!=((first_type==8||first_type==12||first_type==13||first_type==14)))return -22;
    expected=mbx_resource_bytes(r.version);width=r.reserved>>16;height=r.reserved&65535U;
    if(r.version==11){
     if(count!=1||header[1]!=10||header[11]||header[3]||r.reserved!=8||!((header[4]==240&&header[5]==320)||(header[4]==128&&header[5]==128)))return -22;
     expected=0;
    }else if(r.version==9){width=header[4];height=header[5];
     if(count!=1||header[1]!=10||header[11]||header[3]||r.reserved>15||width<16||width>320||height<16||(height>192&&!(width==240&&height==320))||(width&15)||(height&15))return -22;
     expected=width*height*8U;
    }else if(r.version==10){
     if(i||header[1]!=10||header[11]||width!=240||height!=320||header[4]!=240||header[5]!=320)return -22;
     expected=0;
    }else if(r.version==7){
     if(i||header[1]!=10||header[11]||width!=240||height!=320||header[4]!=240||header[5]!=320)return -22;
     expected=width*height*4U;if(expected>MBX_WIRE_LINEAR_PAYLOAD)return -22;
    }else if(r.version==13||r.version==14){
     if((header[1]!=9&&header[1]!=10)||header[11]!=5||r.offset>=(r.version==14?14U:MBX_WINDOW_SLOTS)||!r.reserved||!r.bytes)return -22;
     continue; /* A token occupies no payload bytes or padding. */
    }else if(r.version==12){
     if((header[1]!=9&&header[1]!=10)||header[11]!=5||r.reserved)return -22;expected=32768;
    }else if(r.version==8){
     if((header[1]!=9&&header[1]!=10)||(header[11]!=5&&!((first_type==7||first_type==10)&&header[11]==0))||!width||!height||width>320||height>320)return -22;
     expected=((width+17U)&~15U)*(height+2U)*4U;
    }else if(total>32768)return -22;
    aligned=(r.version==8||r.version==12)?((at+127U)&~127U):at;
    if((!expected&&r.version!=10&&r.version!=11)||r.bytes!=expected||r.offset!=aligned||(r.version!=7&&r.version!=8&&r.version!=9&&r.version!=10&&r.version!=11&&r.reserved)||r.offset>total||r.bytes>total-r.offset)return -22;
    for(pad=at;pad<r.offset;++pad)if(raw[data_offset+pad])return -22;
    at=r.offset+r.bytes;
   }
   if(at!=total)return -22;draw_offset=data_offset+total;
  }
 }
 /* Do not put a 64-entry scratch table on the ARM kernel stack. Publish only
  * after validating the entire input, then copy its immutable descriptors. */
 memset(out,0,sizeof(*out));out->count=count;out->bytes=total;out->data_offset=data_offset;out->draw_offset=draw_offset;
 if(count){if(header[1]<=5)out->item[0]=legacy;else memcpy(out->item,raw+64,16*count);}
 return 0;
}
/* Page number within the driver's already reserved final eight parameter pages.
 * 1..8 is an internal allocation result, never a user-provided address. */
static inline unsigned mbx_wire_resource_page(const struct mbx_wire_resources *r,unsigned index){
 if(!r||index>=r->count||!r->bytes||r->bytes>32768||r->item[index].offset>r->bytes||r->item[index].bytes>r->bytes-r->item[index].offset)return 0;
 return 1+(32768-r->bytes+r->item[index].offset)/4096;
}
/* Append/deduplicate one immutable resource without changing any draw bytes.
 * All capacity, source-overlap and descriptor checks precede the first write. */
static inline int mbx_wire_resource_append(void *data,unsigned capacity,const void *source,unsigned version,unsigned bytes,unsigned *index){
 unsigned char *raw=data;unsigned header[12],i;struct mbx_wire_resources r;
 if(!data||!source||!index||capacity<48||bytes!=mbx_resource_bytes(version)||!bytes)return -22;
 memcpy(header,raw,48);
 if(header[2]>capacity||(header[1]!=2&&header[1]!=6&&header[1]!=9&&header[1]!=10)||mbx_wire_resources_parse(data,header[2],&r))return -22;
 for(i=0;i<r.count;++i)if(r.item[i].version>=7)return -28;
 unsigned long src=(unsigned long)source,dst=(unsigned long)data;
 if((src>=dst&&src-dst<capacity)||(dst>=src&&dst-src<bytes))return -22;
 for(i=0;i<r.count;++i)if(r.item[i].version==version&&r.item[i].bytes==bytes&&!memcmp(raw+r.data_offset+r.item[i].offset,source,bytes)){*index=i;return 0;}
 unsigned data_offset=64+16*(r.count+1),overhead=data_offset-r.data_offset;
 if(r.count==4||bytes>32768-r.bytes||overhead+bytes>capacity-header[2])return -28;
 memmove(raw+data_offset,raw+r.data_offset,header[2]-r.data_offset);
 unsigned draws=data_offset+r.bytes;
 memmove(raw+draws+bytes,raw+draws,header[2]+overhead-draws);
 unsigned table[4]={r.count+1,r.bytes+bytes,0,0};struct mbx_wire_resource desc={version,bytes,r.bytes,0};
 memcpy(raw+48,table,16);memcpy(raw+64+16*r.count,&desc,16);memcpy(raw+data_offset+r.bytes,source,bytes);
 header[1]=header[1]>=9?header[1]:6;header[2]+=overhead+bytes;memcpy(raw+4,header+1,8);*index=r.count;return 0;
}
/* One immutable bordered linear image. Mixed-resource batching remains
 * rejected until GPU surface preservation is admitted. */
static inline int mbx_wire_resource_append_linear(void *data,unsigned capacity,const void *source,unsigned width,unsigned height,unsigned bytes,unsigned *index){
 unsigned char *raw=data;unsigned header[12],i;struct mbx_wire_resources r;
 if(!data||!source||!index||!width||!height||width>320||height>320||bytes!=((width+17U)&~15U)*(height+2U)*4U||capacity<64)return -22;
 memcpy(header,raw,48);
 if((header[1]!=9&&header[1]!=10)||(header[11]!=5&&header[11]!=0)||header[2]>capacity||mbx_wire_resources_parse(data,header[2],&r))return -22;
 unsigned long a=(unsigned long)source,b=(unsigned long)data;
 if((a>=b&&a-b<capacity)||(b>=a&&b-a<bytes))return -22;
 unsigned dimensions=(width<<16)|height;
 for(i=0;i<r.count;++i){
  if(i==0&&(r.item[i].version==7||r.item[i].version==10))continue;
  if(r.item[i].version==12||r.item[i].version==13||r.item[i].version==14)continue;
  if(r.item[i].version!=8)return -28;
  if(r.item[i].bytes==bytes&&r.item[i].reserved==dimensions&&!memcmp(raw+r.data_offset+r.item[i].offset,source,bytes)){*index=i;return 0;}
 }
 unsigned offset=(r.bytes+127U)&~127U,pad=offset-r.bytes;
 if(r.count==64||offset>MBX_WIRE_LINEAR_PAYLOAD||bytes>MBX_WIRE_LINEAR_PAYLOAD-offset||16+pad+bytes>capacity-header[2])return -28;
 unsigned data_offset=r.data_offset+16,draw=data_offset+r.bytes;
 memmove(raw+data_offset,raw+r.data_offset,header[2]-r.data_offset);
 memmove(raw+draw+pad+bytes,raw+draw,header[2]+16-draw);
 memset(raw+draw,0,pad);memcpy(raw+data_offset+offset,source,bytes);
 unsigned table[4]={r.count+1,offset+bytes,0,0};struct mbx_wire_resource item={8,bytes,offset,dimensions};
 memcpy(raw+48,table,16);memcpy(raw+64+16*r.count,&item,16);
 header[2]+=16+pad+bytes;memcpy(raw+8,header+2,4);*index=r.count;return 0;
}
/* Resource index low bits preserve the previous four-slot wire encoding.
 * High bits avoid depth/scissor and the userspace-only alpha annotation. */
static inline unsigned mbx_resource_index_flags(unsigned index){return ((index&3U)<<4)|((index&60U)<<7);}
static inline unsigned mbx_resource_index_decode(unsigned flags){return ((flags>>4)&3U)|((flags>>7)&60U);}
/* Appends one 128x128 twiddled RGB565 image to the guarded arena. */
static inline int mbx_wire_resource_append_rgb565_arena(void *data,unsigned capacity,const void *source,unsigned bytes,unsigned *index){
 unsigned char *raw=data;unsigned h[12],i;struct mbx_wire_resources r;
 if(!data||!source||!index||bytes!=32768||capacity<64)return -22;
 memcpy(h,raw,48);
 if((h[1]!=9&&h[1]!=10)||h[11]!=5||h[2]>capacity||mbx_wire_resources_parse(raw,h[2],&r))return -22;
 unsigned long a=(unsigned long)source,b=(unsigned long)data;
 if((a>=b&&a-b<capacity)||(b>=a&&b-a<bytes))return -22;
 for(i=0;i<r.count;i++){
  if(r.item[i].version!=8&&r.item[i].version!=12)return -28;
  if(r.item[i].version==12&&!memcmp(raw+r.data_offset+r.item[i].offset,source,bytes)){*index=i;return 0;}
 }
 unsigned offset=(r.bytes+127U)&~127U,pad=offset-r.bytes;
 if(r.count==64||offset>MBX_WIRE_LINEAR_PAYLOAD||bytes>MBX_WIRE_LINEAR_PAYLOAD-offset||16+pad+bytes>capacity-h[2])return -28;
 unsigned data_offset=r.data_offset+16,draw=data_offset+r.bytes;
 memmove(raw+draw+pad+bytes,raw+r.draw_offset,h[2]-r.draw_offset);
 memmove(raw+data_offset,raw+r.data_offset,r.bytes);
 memset(raw+draw,0,pad);memcpy(raw+data_offset+offset,source,bytes);
 unsigned table[4]={r.count+1,offset+bytes,0,0};struct mbx_wire_resource item={12,bytes,offset,0};
 memcpy(raw+48,table,16);memcpy(raw+64+16*r.count,&item,16);
 h[2]+=16+pad+bytes;memcpy(raw+8,h+2,4);*index=r.count;return 0;
}
static inline int mbx_resources_use_linear(const struct mbx_wire_resources *r){return r->count&&((r->item[0].version==8)||(r->item[0].version==12)||(r->item[0].version==13)||(r->item[0].version==14)||(r->item[0].version==7)||(r->item[0].version==10)||(r->count==1&&r->item[0].version==9));}
static inline int mbx_wire_resource_append_window_layout(void *data,unsigned capacity,struct mbx_window_token token,unsigned layout,unsigned *index){
 unsigned char *p=data;unsigned h[12],i,kind=layout==2?14:13;struct mbx_wire_resources r;
 if((layout!=1&&layout!=2)||!data||!index||!token.session||!token.generation||token.slot>=(layout==2?14U:MBX_WINDOW_SLOTS)||capacity<64)return -22;
 memcpy(h,p,48);if(h[2]>capacity||h[11]!=5||mbx_wire_resources_parse(data,h[2],&r))return -22;
 for(i=0;i<r.count;i++){
  if(r.item[i].version!=8&&r.item[i].version!=12&&r.item[i].version!=13&&r.item[i].version!=14)return -22;
  if(r.item[i].version==kind&&r.item[i].offset==token.slot&&r.item[i].reserved==token.session&&r.item[i].bytes==token.generation){*index=i;return 0;}
 }
 if(r.count==64||16>capacity-h[2])return -22;
 memmove(p+r.data_offset+16,p+r.data_offset,h[2]-r.data_offset);
 struct mbx_wire_resource d={kind,token.generation,token.slot,token.session};memcpy(p+64+16*r.count,&d,16);
 unsigned table[4]={r.count+1,r.bytes,0,0};memcpy(p+48,table,16);h[2]+=16;memcpy(p,h,48);*index=r.count;return 0;
}
static inline int mbx_wire_resource_append_window(void *data,unsigned capacity,struct mbx_window_token token,unsigned *index){return mbx_wire_resource_append_window_layout(data,capacity,token,1,index);}
#endif
