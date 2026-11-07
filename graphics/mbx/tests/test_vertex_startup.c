/* SPDX-License-Identifier: MIT */
#include "../common/mbx_vertex_program.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    struct mbx_command commands[MBX_VERTEX_STARTUP_WORDS+2],saved[MBX_VERTEX_STARTUP_WORDS+2];
    unsigned i,at,seen[256]={0};
    memset(commands,0xa5,sizeof(commands));memcpy(saved,commands,sizeof(saved));
    assert(mbx_encode_vertex_startup(commands+1,MBX_VERTEX_STARTUP_WORDS-1)==-22);
    assert(!memcmp(saved,commands,sizeof(saved)));
    assert(!mbx_encode_vertex_startup(commands+1,MBX_VERTEX_STARTUP_WORDS));
    assert(!memcmp(saved,commands,sizeof(commands[0])));
    assert(!memcmp(saved+MBX_VERTEX_STARTUP_WORDS+1,commands+MBX_VERTEX_STARTUP_WORDS+1,sizeof(commands[0])));
    for(i=1;i<=MBX_VERTEX_STARTUP_WORDS;++i)assert(commands[i].destination==MBX_FIFO);
    /* Independently inspect the two MOV instruction fields and their bindings. */
    assert(commands[1].value==0x90000001U);
    for(i=0;i<2;++i){
        unsigned low=commands[2+2*i].value,high=commands[3+2*i].value;
        assert((low&31U)==1 && ((low>>8)&255U)==0xe4U && !(low&~0xe401U));
        assert((high>>26)==i && ((high>>22)&15U)==15U);
        assert((high&0x003fffffU)==(i ? 0x10000U : 0));
    }
    assert(commands[6].value==0x8000ffffU && commands[7].value==0x00800100U);
    for(i=8;i<=22;++i)assert(commands[i].value==0x00800100U);
    at=23;
    while(at<=MBX_VERTEX_STARTUP_WORDS){
        unsigned header=commands[at++].value,first=(header>>16)&255U,last=header&255U,count;
        assert((header&0xff00ff00U)==0xa0000000U && first<=last);
        count=4*(last-first+1);assert(count<=MBX_VERTEX_STARTUP_WORDS+1-at);
        for(i=first;i<=last;++i){assert(!seen[i]);seen[i]=1;}
        for(i=0;i<count;++i){
            unsigned bits=commands[at+i].value;
            assert((bits&0x7f800000U)!=0x7f800000U); /* no NaN/Inf constants */
        }
        at+=count;
    }
    assert(at==MBX_VERTEX_STARTUP_WORDS+1);
    for(i=0;i<256;++i)
        assert(seen[i]==(unsigned)(i==0 || i==16 || i==17 || i==83 || i==84 || i==102 || (i>=166 && i<=171)));
    puts("Original VGP startup: MOV bindings, complete sections/constants, finite data, bounds and atomic rejection PASS");
    return 0;
}
