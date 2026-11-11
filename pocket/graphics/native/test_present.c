/* SPDX-License-Identifier: MIT */
#include "present.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include <limits.h>
struct mock { unsigned waits, submits; int fail_wait, fail_submit; };
static int wait_display(void *v) { struct mock *m=v; ++m->waits; return m->fail_wait; }
static int submit_display(void *v) { struct mock *m=v; ++m->submits; return m->fail_submit; }
int main(void)
{
    unsigned char src[48], dst[128], snapshot[128];
    for(unsigned i=0;i<sizeof(src);++i)src[i]=(unsigned char)i;
    memset(dst,0xa5,sizeof(dst));
    struct mock m={0};
    struct mbx_surface s={src,sizeof(src),12,4,4};
    struct mbx_presenter p={{dst,sizeof(dst),16,6,8},
                           {wait_display,submit_display},&m,0,0,0,1,0,0,{0,0,0,0}};
    /* A cropped source with padding must preserve every other byte, including
     * framebuffer padding and surrounding UI. First wait fences old output. */
    assert(!mbx_present_rgb565(&p,&s,(struct mbx_rect){1,1,3,2},2,3));
    assert(m.waits==1 && m.submits==1 && p.copied_bytes==12);
    assert(p.submitted_region.x==2&&p.submitted_region.y==3&&p.submitted_region.width==3&&p.submitted_region.height==2);
    for(unsigned i=0;i<sizeof(dst);++i){
        unsigned row=i/16,col=i%16;
        unsigned char expected=0xa5;
        if(row>=3 && row<5 && col>=4 && col<10)
            expected=src[(row-2)*12+col-2];
        assert(dst[i]==expected);
    }
    memcpy(snapshot,dst,sizeof(dst));
    assert(mbx_present_rgb565(&p,&s,(struct mbx_rect){UINT_MAX,0,2,2},0,0));
    assert(m.waits==1 && !memcmp(snapshot,dst,sizeof(dst)));
    assert(mbx_present_rgb565(&p,&p.framebuffer,(struct mbx_rect){0,0,2,2},0,0));
    assert(m.waits==1);
    m.fail_wait=1;
    assert(mbx_present_rgb565(&p,&s,(struct mbx_rect){0,0,2,2},0,0));
    assert(p.faulted && p.pending && m.submits==1);
    assert(!memcmp(snapshot,dst,sizeof(dst)));
    m.fail_wait=0;
    assert(mbx_present_drain(&p)); /* No implicit recovery on a later call. */
    p.faulted=0;p.pending=0;m.fail_submit=1;
    assert(mbx_present_rgb565(&p,&s,(struct mbx_rect){0,0,2,2},0,0));
    assert(p.faulted && p.pending);
    struct mbx_rect damage;struct mbx_surface other={snapshot,sizeof(snapshot),16,6,8};
    memcpy(snapshot,dst,sizeof(dst));assert(mbx_surface_damage(&p.framebuffer,&other,&damage)==0);
    snapshot[2*16+2*2]^=1;snapshot[5*16+4*2+1]^=1;
    assert(mbx_surface_damage(&p.framebuffer,&other,&damage)==1);
    assert(damage.x==2&&damage.y==2&&damage.width==3&&damage.height==4);
    p.faulted=0;p.pending=1;m.fail_wait=0;m.fail_submit=0;
    struct mbx_surface borrowed;uint64_t copied=p.copied_bytes;
    assert(!mbx_present_acquire(&p,&borrowed));assert(p.writing&&!p.pending&&borrowed.pixels==dst);
    assert(mbx_present_acquire(&p,&borrowed));assert(mbx_present_drain(&p));
    assert(mbx_present_rgb565(&p,&s,(struct mbx_rect){0,0,2,2},0,0));
    assert(mbx_present_submit(&p,(struct mbx_rect){6,0,1,1})&&p.writing);
    assert(!mbx_present_cancel(&p)&&!p.writing);assert(!mbx_present_acquire(&p,&borrowed));
    memset(borrowed.pixels,0x36,borrowed.bytes);
    assert(!mbx_present_submit(&p,(struct mbx_rect){0,0,6,8}));assert(p.pending&&!p.writing&&p.copied_bytes==copied);
    assert(!mbx_present_drain(&p));assert(!mbx_present_acquire(&p,&borrowed));m.fail_submit=1;
    assert(mbx_present_submit(&p,(struct mbx_rect){0,0,6,8}));assert(p.faulted&&p.pending&&!p.writing);
    assert(mbx_present_acquire(&p,&borrowed));
    puts("PASS: exact RGB565 crop, padding, bounds, alias rejection, display fences and retained failures");
}
