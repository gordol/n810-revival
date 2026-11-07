/* SPDX-License-Identifier: MIT */
#include "present.h"
#include <string.h>
#include <stdint.h>

static int valid(const struct mbx_surface *s)
{
    return s && s->pixels && s->width && s->height &&
           s->width <= s->stride / 2 &&
           s->stride && s->height <= s->bytes / s->stride;
}
int mbx_present_drain(struct mbx_presenter *p)
{
    if (!p || p->faulted || !p->ops.wait) return -1;
    if (!p->pending) return 0;
    if (p->ops.wait(p->context)) { p->faulted = 1; return -1; }
    p->pending = 0; ++p->completed;
    return 0;
}
int mbx_present_rgb565(struct mbx_presenter *p, const struct mbx_surface *s,
                      struct mbx_rect r, unsigned x, unsigned y)
{
    if (!p || p->faulted || !p->ops.wait || !p->ops.submit ||
        !valid(s) || !valid(&p->framebuffer)) return -1;
    struct mbx_surface *d = &p->framebuffer;
    if (!r.width || !r.height || r.x > s->width || r.y > s->height ||
        r.width > s->width-r.x || r.height > s->height-r.y ||
        x > d->width || y > d->height ||
        r.width > d->width-x || r.height > d->height-y) return -1;
    /* Reject aliased mappings: row-wise copying cannot safely handle every
     * overlap. An owner must provide disjoint GPU and framebuffer mappings. */
    uintptr_t sa=(uintptr_t)s->pixels, da=(uintptr_t)d->pixels;
    if (s->bytes > UINTPTR_MAX-sa || d->bytes > UINTPTR_MAX-da ||
        (sa < da+d->bytes && da < sa+s->bytes)) return -1;
    if (mbx_present_drain(p)) return -1;
    for (unsigned row=0; row<r.height; ++row)
        memcpy((unsigned char *)d->pixels+(y+row)*d->stride+(size_t)x*2,
               (const unsigned char *)s->pixels+(r.y+row)*s->stride+(size_t)r.x*2,
               (size_t)r.width*2);
    p->copied_bytes += (uint64_t)r.width*r.height*2;
    /* Even an unsuccessful submission may have reached hardware. Retain
     * ownership on failure; never pretend that it is safe to reuse memory. */
    p->submitted_region=(struct mbx_rect){x,y,r.width,r.height};
    p->pending = 1;
    if (p->ops.submit(p->context)) { p->faulted = 1; return -1; }
    ++p->submitted;
    return 0;
}

int mbx_surface_damage(const struct mbx_surface *a,const struct mbx_surface *b,struct mbx_rect *r)
{
    if(!r||!valid(a)||!valid(b)||a->width!=b->width||a->height!=b->height)return -1;
    unsigned left=a->width,top=a->height,right=0,bottom=0;
    for(unsigned y=0;y<a->height;++y){
        const unsigned char *ap=(const unsigned char *)a->pixels+y*a->stride,*bp=(const unsigned char *)b->pixels+y*b->stride;
        if(!memcmp(ap,bp,(size_t)a->width*2))continue;
        if(y<top)top=y;
        bottom=y+1;
        for(unsigned x=0;x<a->width;++x)if(memcmp(ap+x*2,bp+x*2,2)){
            if(x<left)left=x;
            if(x+1>right)right=x+1;
        }
    }
    *r=right?(struct mbx_rect){left,top,right-left,bottom-top}:(struct mbx_rect){0,0,0,0};
    return right?1:0;
}
