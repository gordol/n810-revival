#include "resident_checkpoint_wire.h"
static bool mbx_resident_requested(void)
{const char *v=getenv("N810_MBX_RESIDENT_CHECKPOINT");return v&&!strcmp(v,"1");}
static void mbx_resident_materialize(struct sp_mbx_capture *c,bool expand)
{
 if(!c->resident_dirty)return;
 if(!c->reference_target||!c->pixels||!c->vgp)mbx_fail("resident target lost");
 struct softpipe_resource *r=softpipe_resource(c->reference_target);
 if(r->base.format!=PIPE_FORMAT_B8G8R8A8_UNORM||r->dt||r->stride[0]<960)
  mbx_fail("resident materialization target changed");
 size_t got=0;while(got<307200){ssize_t n=read(c->gpu_fd,(char*)c->pixels+got,307200-got);
  if(n<=0)mbx_fail("resident materialization read failed");got+=n;}
 for(unsigned y=0;y<320;++y)memcpy((char*)r->data+y*r->stride[0],(char*)c->pixels+y*960,960);
 if(++c->vgp->resource_epoch==0)mbx_fail("resource epoch exhausted");
 if(expand&&mbx_resident_expand(c->vgp->data,sizeof(c->vgp->data),c->pixels))
  mbx_fail("resident materialization expansion failed");
 c->resident_dirty=false;c->resident_read_bytes+=got;
}
