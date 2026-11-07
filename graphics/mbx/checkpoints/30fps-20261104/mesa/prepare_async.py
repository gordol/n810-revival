def direct_present_slot(s):
 # Presentation has no payload. Build only the small header in a reserved slot,
 # rather than reserving the maximum vertex packet on the application stack.
 old="""      struct mbx_async_command c;memset(&c,0,offsetof(struct mbx_async_command,packet));
      c.kind=2;c.width=xlib_dt->width;c.height=xlib_dt->height;c.stride=xlib_dt->stride;
      c.depth=xlib_drawable->depth;c.drawable=xlib_drawable->drawable;c.visual=XVisualIDFromVisual(xlib_drawable->visual);
      c.x=box->x;c.y=box->y;c.w=box->width;c.h=box->height;
      mbx_async_enqueue(&c);return;"""
 new="""      struct mbx_async_command *c=mbx_async_reserve();
      memset(c,0,offsetof(struct mbx_async_command,packet));
      c->kind=2;c->width=xlib_dt->width;c->height=xlib_dt->height;c->stride=xlib_dt->stride;
      c->depth=xlib_drawable->depth;c->drawable=xlib_drawable->drawable;c->visual=XVisualIDFromVisual(xlib_drawable->visual);
      c->x=box->x;c->y=box->y;c->w=box->width;c->h=box->height;
      mbx_async_publish();return;"""
 if old in s:return s.replace(old,new)
 assert 'struct mbx_async_command *c=mbx_async_reserve();' in s
 return s

def prepare_async(path):
 s=path.read_text()
 if '#include "mbx_async_image.h"' in s:
  s=s.replace(' struct mbx_async_command c;memset(&c,0,offsetof(struct mbx_async_command,packet));\n c.kind=1;c.bytes=bytes;memcpy(c.packet,packet,bytes);mbx_async_enqueue(&c);return 0;', ' mbx_async_enqueue_packet(packet,bytes);return 0;')
  path.write_text(direct_present_slot(s));return
 s=s.replace('#include "mbx_shared_image.h"','#include "mbx_shared_image.h"\n#include "mbx_async_image.h"')
 s=s.replace('   struct mbx_shared_image *mbx_shared;','   struct mbx_shared_image *mbx_shared;\n   bool mbx_async_owner;')
 bridge='''int n810_mbx_async_submit(struct sw_displaytarget *dt,int fd,const void *packet,size_t bytes,size_t image_bytes)
{
 struct xlib_displaytarget *d=xlib_displaytarget(dt);
 if(!bytes||bytes>MBX_ASYNC_PACKET_BYTES)return -1;
 if(mbx_async_acquire(d->display,fd,image_bytes,&d->mbx_async_owner))return -1;
 mbx_async_enqueue_packet(packet,bytes);return 0;
}
'''
 s=s.replace('static volatile int XErrorFlag = 0;',bridge+'\nstatic volatile int XErrorFlag = 0;')
 s=s.replace('   mbx_shared_destroy(xlib_dt->mbx_shared);','   mbx_async_release(&xlib_dt->mbx_async_owner);\n   mbx_shared_destroy(xlib_dt->mbx_shared);')
 s=s.replace('   if(xlib_dt->mbx_shared&&(flags&PIPE_MAP_READ))', '   if(xlib_dt->mbx_async_owner&&(flags&PIPE_MAP_READ))return mbx_async_read_map();\n   if(xlib_dt->mbx_shared&&(flags&PIPE_MAP_READ))')
 anchor='   if(xlib_dt->mbx_shared){'
 assert s.count(anchor)==1
 s=s.replace(anchor,'''   if(xlib_dt->mbx_async_owner){
      struct mbx_async_command c;memset(&c,0,offsetof(struct mbx_async_command,packet));
      c.kind=2;c.width=xlib_dt->width;c.height=xlib_dt->height;c.stride=xlib_dt->stride;
      c.depth=xlib_drawable->depth;c.drawable=xlib_drawable->drawable;c.visual=XVisualIDFromVisual(xlib_drawable->visual);
      c.x=box->x;c.y=box->y;c.w=box->width;c.h=box->height;
      mbx_async_enqueue(&c);return;
   }
'''+anchor)
 path.write_text(direct_present_slot(s))
