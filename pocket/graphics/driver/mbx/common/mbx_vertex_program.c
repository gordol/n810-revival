/* SPDX-License-Identifier: MIT */
#include "mbx_vertex_program.h"

/* MOV: opcode1, identity source swizzle, destination selector and four-lane
 * write mask. Source bank0 is vertex input, bank2 is temporary. These fields
 * were recovered by the project's original offline VGP codec in October.
 * Keep this restricted encoder independent of that research's vendor inputs. */
static void move(unsigned destination,unsigned bank,unsigned source,unsigned words[2])
{
    words[0]=1U|(0xe4U<<8);
    words[1]=(destination<<26)|(15U<<22)|(bank<<16)|source;
}

int mbx_encode_vertex_startup(struct mbx_command *commands,unsigned capacity)
{
    unsigned words[MBX_VERTEX_STARTUP_WORDS],i;
    if(!commands || capacity<MBX_VERTEX_STARTUP_WORDS)return -22;
    /* Independent MOVs avoid a temporary read-after-write dependency.
     * Mesa's draw module owns transformation and lighting. */
    words[0]=0x90000001U;
    move(0,0,0,words+1);   /* output position = input position */
    move(1,1,0,words+3);   /* output diffuse = explicit float constant0 */
    /* Bind the same two independent pass-through MOVs at every stage. This
     * isolates stage dispatch from input-format binding: whichever stage the
     * pretransformed format selects must publish the same explicit outputs.
     * Every descriptor spans instructions0..1 with one invocation. */
    words[5]=0x8000ffffU;
    /* Nokia's direct input-to-output stage descriptors carry bit23
     * (e.g. program58 at804c3150). Its complete semantics remain unresolved;
     * use the observed direct-output configuration, not a zero high field. */
    words[6]=0x00800100U;
    for(i=7;i<22;++i)words[i]=0x00800100U;
    /* The TA's clipping/packing constants are shared even by a pass-through
     * program. Keep them explicit instead of leaving zero clip planes after
     * reset. These are data vectors, not recovered executable instructions. */
    {
        unsigned at=22,j;
        const unsigned near_far[8]={0,0,0x3f800000U,0x3f800000U,
                                    0,0,0xbf800000U,0x3f800000U};
        const unsigned packing[8]={0,0,0x3f800000U,0,
                                    0x40e00000U,0x3f808084U,0x40e00000U,0x40e00000U};
        words[at++]=0xa0100011U;
        for(j=0;j<8;++j)words[at++]=near_far[j];
        words[at++]=0xa0530054U;
        for(j=0;j<8;++j)words[at++]=packing[j];
        words[at++]=0xa0660066U;
        for(j=0;j<4;++j)words[at++]=0x00800000U;
        words[at++]=0xa0a600a8U;
        for(j=0;j<12;++j)words[at++]=(j%5U)==0 ? 0x3f800000U : 0;
        words[at++]=0xa0a900abU;
        for(j=0;j<12;++j)words[at++]=(j%5U)==0 ? 0x40e00000U : 0;
        words[at++]=0xa0000000U;
        words[at++]=0;words[at++]=0x3f800000U;
        words[at++]=0;words[at++]=0x3f800000U;
    }
    for(i=0;i<MBX_VERTEX_STARTUP_WORDS;++i)
        commands[i]=(struct mbx_command){MBX_FIFO,words[i]};
    return 0;
}
