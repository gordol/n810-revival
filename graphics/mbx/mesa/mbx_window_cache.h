/* SPDX-License-Identifier: MIT */
static bool mbx_windows_requested(void){const char *v=getenv("N810_MBX_WINDOW_IMAGES");return v&&!strcmp(v,"1");}
static int mbx_window_find(struct sp_mbx_capture *c,struct pipe_resource *r){
 for(unsigned i=0;i<14;i++)if(c->window[i].resource==r&&c->window[i].token.generation&&c->window[i].timestamp==softpipe_resource(r)->timestamp)return i;
 return -1;
}
static unsigned mbx_window_choose(struct sp_mbx_capture *c,struct pipe_resource *r){
 int selected=-1;
 for(unsigned i=0;i<14;i++){
  if(c->window[i].resource==r){selected=i;break;}
  if(selected<0&&(!c->window[i].resource||p_atomic_read(&c->window[i].resource->reference.count)==1))selected=i;
 }
 if(selected<0)mbx_fail("rendered window cache exhausted; no CPU fallback");
 struct mbx_window_entry *e=&c->window[selected];pipe_resource_reference(&e->resource,r);e->token=(struct mbx_window_token){0};return selected;
}
static void mbx_window_bind_target(struct sp_mbx_capture *c,unsigned slot){
 struct mbx_window_request q={.version=1,.destination=slot};
 if(ioctl(c->gpu_fd,MBX_WINDOW_BIND,&q))mbx_fail("rendered image target rejected");
}
