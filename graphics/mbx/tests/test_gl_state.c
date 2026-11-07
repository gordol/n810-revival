/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include "../common/mbx_gl_state.h"
int main(void)
{
    struct mbx_gl_state s={1,1,7,0,0,15};
    unsigned w[2];
    assert(!mbx_gl_state_words(&s,w));
    assert(w[0]==0xe0000000U && w[1]==0x22200e00U);
    s.depth_write=0;assert(!mbx_gl_state_words(&s,w));
    assert(w[1]==0x22200e80U);
    for(unsigned i=0;i<8;++i){
        s.depth_func=i;s.depth_write=1;
        assert(!mbx_gl_state_words(&s,w));assert(((w[1]>>9)&7)==i);
    }
    s.depth_enabled=0;assert(!mbx_gl_state_words(&s,w));
    assert((w[1]&0xe80)==0xe80);
    s.smooth_color=1;assert(!mbx_gl_state_words(&s,w));
    assert(w[1]&0x400000);
    s.blend_enabled=1;w[0]=123;w[1]=456;
    assert(mbx_gl_state_words(&s,w)==-22 && w[0]==123 && w[1]==456);
    assert(mbx_gl_pack_rgba(255,0,0,255)==0xff0000ffU);
    assert(mbx_gl_pack_rgba(0,255,0,255)==0xff00ff00U);
    assert(mbx_gl_pack_rgba(0,0,255,255)==0xffff0000U);
    return 0;
}
