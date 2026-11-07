/* SPDX-License-Identifier: MIT */
#include "../common/mbx_packets.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>

int main(void)
{
    const unsigned expected[19]={0x10000063,0x14202f80,0xe0000000,0x503,0,
        0x40000000,0x300b0800,0,0,0x3f800000,0x7f00ff00,
        0x42800000,0,0x3f800000,0x7f00ff00,0,0x42800000,0x3f800000,0x7f00ff00};
    struct mbx_vertex vertices[3]={{0,0,0x3f800000,0xff00ff00},
        {0x42800000,0,0x3f800000,0xff00ff00},{0,0x42800000,0x3f800000,0xff00ff00}};
    unsigned words[21],before[21],bad[]={0x80000000,0x7f800000,0x7fc00000,0x42800001};
    unsigned i;
    for(i=0;i<21;++i)words[i]=0xa5a5a5a5;
    assert(!mbx_encode_triangle(32,32,vertices,words+1,19));
    assert(words[0]==0xa5a5a5a5&&words[20]==0xa5a5a5a5);
    assert(!memcmp(words+1,expected,sizeof(expected)));
    memcpy(before,words,sizeof(words));
    for(i=0;i<sizeof(bad)/sizeof(bad[0]);++i){
        vertices[0].x=bad[i];
        assert(mbx_encode_triangle(32,32,vertices,words+1,19)==-22);
        assert(!memcmp(words,before,sizeof(words)));
    }
    vertices[0].x=0;
    assert(mbx_encode_triangle(32,32,vertices,words+1,18)==-22);
    vertices[1].argb=0x7f00ff00;
    assert(mbx_encode_triangle(32,32,vertices,words+1,19)==-22);
    assert(!memcmp(words,before,sizeof(words)));
    {
        struct mbx_command commands[25],saved[25];
        vertices[1].argb=0xff00ff00;
        memset(commands,0xa5,sizeof(commands));
        assert(!mbx_encode_triangle_frame(32,32,vertices,commands+1,23));
        assert(commands[1].destination==MBX_FIFO && commands[1].value==0x10000010U);
        assert(commands[2].destination==MBX_FIFO && commands[2].value==0);
        for(i=0;i<19;++i){assert(commands[i+3].destination==MBX_FIFO);assert(commands[i+3].value==expected[i]);}
        assert(commands[22].destination==MBX_POLYGON_CONTROL && commands[22].value==1);
        assert(commands[23].destination==MBX_FIFO && commands[23].value==0xf0000000U);
        assert(commands[0].value==0xa5a5a5a5 && commands[24].value==0xa5a5a5a5);
        memcpy(saved,commands,sizeof(commands));
        assert(mbx_encode_triangle_frame(32,32,vertices,commands+1,20)==-22);
        vertices[0].z=0x7f800000;
        assert(mbx_encode_triangle_frame(32,32,vertices,commands+1,23)==-22);
        assert(!memcmp(saved,commands,sizeof(commands)));
    }
    vertices[0]=(struct mbx_vertex){0,0,0x3f800000,0xff112233};
    vertices[1].argb=0xff00ff00;
    assert(!mbx_encode_triangle(32,32,vertices,words+1,19));
    assert(words[11]==0x7f332211U);
    puts("MBX packet: Nokia reference match, positive RGBA container, RGB preservation, bounds and atomic rejection PASS");
    return 0;
}
