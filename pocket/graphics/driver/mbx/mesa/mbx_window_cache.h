/* SPDX-License-Identifier: MIT */
#include "mbx_window_export.h"
#include "mbx_job_lock.h"
/* Contexts in one process must not silently claim the same broker range. */
static struct sp_mbx_capture *mbx_window_owners[14];
static int mbx_window_claim(struct sp_mbx_capture *c){
 int error;if(!mbx_window_range_valid(c->window_first,c->window_count))return -EINVAL;
 error=mbx_job_enter();if(error)return error;
 for(unsigned i=c->window_first;i<c->window_first+c->window_count;i++)
  if(mbx_window_owners[i]&&mbx_window_owners[i]!=c){mbx_job_leave();return -EBUSY;}
 for(unsigned i=c->window_first;i<c->window_first+c->window_count;i++)mbx_window_owners[i]=c;
 return mbx_job_leave();
}
static int mbx_window_retire(struct sp_mbx_capture *c){
 int error=mbx_job_enter();if(error)return error;
 for(unsigned i=0;i<14;i++)if(c->window[i].exported){mbx_job_leave();return -EBUSY;}
 for(unsigned i=0;i<14;i++)if(mbx_window_owners[i]==c)mbx_window_owners[i]=NULL;
 return mbx_job_leave();
}
static unsigned mbx_window_env_unsigned(const char *name){
 const char *text=getenv(name);char *end;unsigned long value;
 if(!text||!*text)mbx_fail("shared window slot range missing");
 errno=0;value=strtoul(text,&end,10);
 if(*end||errno||value>UINT_MAX)mbx_fail("shared window slot range malformed");
 return (unsigned)value;
}
static void mbx_window_client_range(struct sp_mbx_capture *c,int inherited){
 int shared=mbx_job_shared();if(shared<0)mbx_fail("GPU job lock invalid");
 c->window_first=0;c->window_count=14;c->shared_jobs=shared>0;c->window_layout=1;
 const char *images=getenv("N810_MBX_WINDOW_IMAGES"),*native=getenv("N810_MBX_NATIVE_WINDOWS");
 if(images&&!strcmp(images,"1")){
  struct mbx_window_layout caps;
  if(!ioctl(c->gpu_fd,MBX_WINDOW_LAYOUT,&caps)){
   if(!mbx_window_layout_valid(&caps))mbx_fail("window layout capability mismatch");
   c->window_layout=caps.version;
  }else if(errno!=ENOTTY)mbx_fail("window layout capability query failed");
 }
 if(native&&!strcmp(native,"1")&&c->window_layout!=2)mbx_fail("native-size windows require matching module capabilities");
 if(shared){
  if(inherited<0)mbx_fail("shared window clients require the inherited render owner");
  c->window_first=mbx_window_env_unsigned("N810_MBX_WINDOW_FIRST");
  c->window_count=mbx_window_env_unsigned("N810_MBX_WINDOW_COUNT");
  if(!mbx_window_range_valid(c->window_first,c->window_count))mbx_fail("shared window slot range invalid");
  const char *exclusive[]={"N810_MBX_TEMPLATE","N810_MBX_ASYNC","N810_MBX_SHARED_IMAGE","N810_MBX_RESIDENT_CHECKPOINT","N810_MBX_RESIDENT_ALPHA"};
  for(unsigned i=0;i<sizeof(exclusive)/sizeof(exclusive[0]);++i){const char *v=getenv(exclusive[i]);if(v&&!strcmp(v,"1"))mbx_fail("shared clients require synchronous window images");}
  if(mbx_window_claim(c))mbx_fail("shared window range already belongs to another context");
 }else if(getenv("N810_MBX_WINDOW_FIRST")||getenv("N810_MBX_WINDOW_COUNT"))mbx_fail("window slot partition requires a job lock");
}

static bool mbx_windows_requested(void){const char *v=getenv("N810_MBX_WINDOW_IMAGES");return v&&!strcmp(v,"1");}
static int mbx_window_find(struct sp_mbx_capture *c,struct pipe_resource *r){
 for(unsigned i=0;i<14;i++)if(c->window[i].resource==r&&c->window[i].token.generation&&c->window[i].timestamp==softpipe_resource(r)->timestamp)return i;
 return -1;
}
static int mbx_window_available(struct sp_mbx_capture *c,struct pipe_resource *r){
 int selected=-1;
 for(unsigned i=c->window_first;i<c->window_first+c->window_count;i++){
  if(!mbx_window_shape(c->window_layout,i,r->width0,r->height0))continue;
  if(c->window[i].resource==r){if(c->window[i].exported)return -EBUSY;selected=i;break;}
  if(selected<0&&!c->window[i].exported&&(!c->window[i].resource||p_atomic_read(&c->window[i].resource->reference.count)==1))selected=i;
 }
 return selected<0?-ENOSPC:selected;
}
static unsigned mbx_window_choose(struct sp_mbx_capture *c,struct pipe_resource *r){
 int selected=mbx_window_available(c,r);
 if(selected<0)mbx_fail("rendered window cache exhausted; no CPU fallback");
 struct mbx_window_entry *e=&c->window[selected];pipe_resource_reference(&e->resource,r);e->token=(struct mbx_window_token){0};e->imported=e->exported=false;return selected;
}
static void mbx_window_bind_target(struct sp_mbx_capture *c,unsigned slot){
 struct mbx_window_request q={.version=c->window_layout,.destination=slot};
 if(ioctl(c->gpu_fd,MBX_WINDOW_BIND,&q))mbx_fail("rendered image target rejected");
}
