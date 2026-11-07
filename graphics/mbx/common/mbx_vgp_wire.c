/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_wire.h"
#include "mbx_vgp_transform.h"
_Static_assert(sizeof(struct mbx_vgp_wire_frame)==48,"wire frame layout");
_Static_assert(sizeof(struct mbx_vgp_wire_draw)==64,"wire draw layout");
unsigned mbx_vgp_wire_draw_bytes(const struct mbx_vgp_draw *d)
{
 if(!d||!d->instructions||d->instructions>128||d->uniform_count>83||d->immediate_count>6||
    (d->input_count!=1&&d->input_count!=2)||!d->vertex_count||d->vertex_count>4096||
    !d->triangle_count||d->triangle_count>256)return 0;
 return 64+8*d->instructions+16*(d->uniform_count+d->immediate_count+d->input_count*d->vertex_count)+
        ((6*d->triangle_count+3)&~3U);
}
static unsigned mbx_half_extent(unsigned n)
{
 unsigned exponent=0,m=n;
 while(m>>=1)++exponent;
 return ((exponent+126)<<23)|((n<<(23-exponent))&0x7fffff);
}
int mbx_vgp_wire_encode(const void *data,unsigned bytes,struct mbx_command *commands,
                        unsigned capacity,unsigned *written)
{
 const struct mbx_vgp_wire_frame *f=data;
 const unsigned char *raw=data;
 unsigned offset=48,at=0,n,i,total=0;int error;
 if(!data||((unsigned long)data&3)||!commands||!written||bytes<48||bytes>MBX_VGP_WIRE_MAX_BYTES||
    f->magic!=MBX_VGP_WIRE_MAGIC||f->version!=1||f->bytes!=bytes||f->draws>64||
    !f->width||f->width>512||!f->height||f->height>512||(f->width&1)||
    (f->clear_color[0]&0x7fffffff)||(f->clear_color[1]&0x7fffffff)||(f->clear_color[2]&0x7fffffff)||
    f->clear_color[3]>0x3f800000U||f->clear_depth!=0x3f800000U||f->clear_buffers!=5)return -22;
 error=mbx_vgp_frame_begin(commands,capacity,&n);if(error)return error;at+=n;
 {
  unsigned program[16];
  static const unsigned uniform[20]={0x3f800000,0,0,0,0,0x3f800000,0,0,
    0,0,0x3f800000,0,0,0,0,0x3f800000,0,0,0,0x3f800000};
  static const unsigned vertices[16]={0xbf800000,0xbf800000,0x3f800000,0x3f800000,
    0x3f800000,0xbf800000,0x3f800000,0x3f800000,0xbf800000,0x3f800000,0x3f800000,0x3f800000,
    0x3f800000,0x3f800000,0x3f800000,0x3f800000};
  static const unsigned short indices[6]={0,1,2,1,3,2};
  struct mbx_vgp_draw clear={.program=program,.uniforms=uniform,.vertices=vertices,.indices=indices,
    .instructions=8,.uniform_count=5,.input_count=1,.vertex_count=4,.triangle_count=2,.depth_always=1};
  clear.viewport[0]=clear.viewport[1]=mbx_half_extent(f->width);
  clear.viewport[2]=mbx_half_extent(f->height);clear.viewport[3]=clear.viewport[2]|0x80000000;
  clear.viewport[4]=clear.viewport[5]=0x3f000000;
  if(mbx_vgp_transform(0,4,112,program,16)!=8)return -22;
  error=mbx_vgp_draw_encode(&clear,commands+at,capacity-at,&n);if(error)return error;at+=n;
 }
 for(i=0;i<f->draws;++i){
  const struct mbx_vgp_wire_draw *h;
  const unsigned *p;
  struct mbx_vgp_draw d={0};unsigned record,j,padding;
  if(bytes-offset<64)return -22;
  h=(const void *)(raw+offset);
  d.instructions=h->instructions;d.uniform_count=h->uniforms;d.immediate_count=h->immediates;
  d.input_count=h->inputs;d.vertex_count=h->vertices;d.triangle_count=h->triangles;
  d.smooth=h->smooth;d.cull_mode=h->cull_mode;
  for(j=0;j<6;++j)d.viewport[j]=h->viewport[j];
  record=mbx_vgp_wire_draw_bytes(&d);
  if(!record||h->bytes!=record||record>bytes-offset||h->reserved||total+d.triangle_count>2048)return -22;
  total+=d.triangle_count;p=(const void *)(h+1);
  d.program=p;p+=2*d.instructions;d.uniforms=p;p+=4*d.uniform_count;
  d.immediates=p;p+=4*d.immediate_count;d.vertices=p;p+=4*d.input_count*d.vertex_count;
  d.indices=(const void *)p;
  padding=(4-(6*d.triangle_count&3))&3;
  for(j=0;j<padding;++j)if(raw[offset+record-1-j])return -22;
  error=mbx_vgp_draw_encode(&d,commands+at,capacity-at,&n);if(error)return error;at+=n;
  offset+=record;
 }
 if(offset!=bytes)return -22;
 error=mbx_vgp_frame_end(commands+at,capacity-at,&n);if(error)return error;at+=n;
 *written=at;return 0;
}
