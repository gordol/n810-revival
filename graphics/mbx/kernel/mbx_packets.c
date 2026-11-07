/* SPDX-License-Identifier: MIT */
#include "mbx_packets.h"
_Static_assert(sizeof(unsigned)==4,"MBX packets require32bit words");
_Static_assert(sizeof(struct mbx_vertex)==16,"unexpected vertex padding");

static unsigned integer_float(unsigned n)
{
    unsigned exponent=0,value=n;
    if(!n)return 0;
    while(value>1U){value>>=1;++exponent;}
    return ((127U+exponent)<<23)|((n<<(23U-exponent))&0x7fffffU);
}

int mbx_encode_triangle(unsigned width,unsigned height,
                        const struct mbx_vertex vertices[3],
                        unsigned *words,unsigned capacity)
{
    unsigned i,xlimit,ylimit;
    if(!vertices||!words||!width||!height||width>1024||height>1024||capacity<19)
        return -22;
    xlimit=integer_float(width*2U);ylimit=integer_float(height*2U);
    for(i=0;i<3;++i){
        if(vertices[i].x>xlimit||vertices[i].y>ylimit||
           vertices[i].z<0x37800000U||vertices[i].z>0x47800000U||
           (vertices[i].argb>>24)!=255U)return -22;
    }
    /* Validate the complete primitive before touching the output buffer. */
    words[0]=0x10000063U;words[1]=0x14202f80U;words[2]=0xe0000000U;
    words[3]=0x503U;words[4]=0;
    /* Special format mask800 has first set bit11. Nokia804b4558..60
     * inserts that index at bits16+, then804b4588 ORs the mask itself. */
    words[5]=0x40000000U;words[6]=0x300b0800U;
    for(i=0;i<3;++i){
        words[7+4*i]=vertices[i].x;words[8+4*i]=vertices[i].y;
        unsigned color=vertices[i].argb;
        words[9+4*i]=vertices[i].z;
        /* Special attribute11 takes packed RGBA bytes in a positive float
         * container. Nokia8049d87c forces the fourth component to0.5 before
         * 8049e300 packs R,G,B at bits0,8,16 and the container byte at24.
         * Public input is opaque ARGB; preserve RGB and swap R/B for the wire.
         * Passingff as the container byte makes the value negative. */
        words[10+4*i]=0x7f000000U|(color&0x0000ff00U)|
            ((color&255U)<<16)|((color>>16)&255U);
    }
    return 0;
}

int mbx_encode_triangle_batch(unsigned width,unsigned height,
                             const struct mbx_vertex *vertices,unsigned triangles,
                             struct mbx_command *commands,unsigned capacity,
                             unsigned *written)
{
    unsigned packet[MBX_TRIANGLE_WORDS],i,j,cursor=0,needed;
    int error;
    if(!vertices || !commands || !written || !triangles ||
       triangles>MBX_MAX_BATCH_TRIANGLES)return -22;
    needed=triangles*20U+3U;
    if(capacity<needed)return -22;
    /* Reject the entire batch before touching command memory. This keeps a bad
     * late primitive from exposing an incomplete frame to its caller. */
    for(i=0;i<triangles;++i){
        error=mbx_encode_triangle(width,height,vertices+3*i,packet,MBX_TRIANGLE_WORDS);
        if(error)return error;
    }
    /* New-surface preamble8049f574 ->804a6f98, literal804a7f48.
     * Emit once per frame, after validating every primitive. */
    commands[cursor++]=(struct mbx_command){MBX_FIFO,0x10000010U};
    commands[cursor++]=(struct mbx_command){MBX_FIFO,0};
    for(i=0;i<triangles;++i){
        mbx_encode_triangle(width,height,vertices+3*i,packet,MBX_TRIANGLE_WORDS);
        for(j=0;j<MBX_TRIANGLE_WORDS;++j){
            commands[cursor].destination=MBX_FIFO;
            commands[cursor++].value=packet[j];
        }
        commands[cursor].destination=MBX_POLYGON_CONTROL;
        commands[cursor++].value=1;
    }
    /* The recovered flush emits this once per frame, not once per polygon. */
    commands[cursor].destination=MBX_FIFO;commands[cursor++].value=0xf0000000U;
    *written=cursor;
    return 0;
}

int mbx_encode_triangle_frame(unsigned width,unsigned height,
                             const struct mbx_vertex vertices[3],
                             struct mbx_command *commands,unsigned capacity)
{
    unsigned written;
    return mbx_encode_triangle_batch(width,height,vertices,1,commands,capacity,&written);
}
