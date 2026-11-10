/* SPDX-License-Identifier: MIT. Compile actual private API against tiny GL/Gallium fixtures. */
#define _POSIX_C_SOURCE 200809L
#define MBX_WINDOW_EXPORT_TEST
#define MBX_JOB_LOCK_H
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mbx_image_abi.h"
#define GL_TEXTURE_2D 1
#define PIPE_TEXTURE_2D 1
#define PIPE_FORMAT_R8G8B8A8_UNORM 1
#define PIPE_FORMAT_B8G8R8A8_UNORM 2
#include "../mesa/mbx_surface_content.h"
struct pipe_resource {unsigned target,last_level,width0,height0,depth0,array_size,format;struct {int count;}reference;};
struct softpipe_resource {struct pipe_resource base;unsigned timestamp;void *dt;struct mbx_surface_content mbx_content;};
struct mbx_window_entry {struct pipe_resource *resource;struct mbx_window_token token;unsigned timestamp;bool imported,exported;};
struct sp_mbx_capture {struct mbx_window_entry window[14];unsigned window_first,window_count,window_layout;bool shared_jobs;int gpu_fd;struct {unsigned magic,triangles;}header;unsigned rendered_count;struct {struct {unsigned valid;}textures;}*vgp;};
struct softpipe_context {int unused;};
struct gl_texture_image {unsigned NumSamples;struct pipe_resource *pt;};
struct gl_texture_object {unsigned Target;struct {unsigned BaseLevel;}Attrib;struct gl_texture_image *Image[1][1];struct pipe_resource *pt;};
struct st_context {struct softpipe_context *pipe;};
struct gl_context {struct st_context *st;};
static struct sp_mbx_capture client;
static struct softpipe_resource resources[3];
static struct gl_texture_image images[3];
static struct gl_texture_object objects[3];
static struct softpipe_context pipe_ctx;
static struct st_context state={&pipe_ctx};
static struct gl_context context={&state};
static struct gl_context *_mesa_get_current_context(void){return &context;}
static struct gl_texture_object *_mesa_lookup_texture(struct gl_context *ctx,unsigned id){(void)ctx;return id&&id<=3?objects+id-1:NULL;}
static struct softpipe_context *softpipe_context(struct softpipe_context *p){return p;}
static struct softpipe_resource *softpipe_resource(struct pipe_resource *p){return (void*)p;}
static struct sp_mbx_capture *capture(struct softpipe_context *p){(void)p;return &client;}
static void pipe_resource_reference(struct pipe_resource **to,struct pipe_resource *from){*to=from;}
static int p_atomic_read(int *p){return *p;}
static void mbx_fail(const char *s){fprintf(stderr,"unexpected fatal: %s\n",s);abort();}
static int mbx_job_shared(void){return 1;}
static int mbx_job_enter(void){return 0;}
static int mbx_job_leave(void){return 0;}
struct mbx_job_scope {unsigned active;};
static void mbx_job_scope_end(struct mbx_job_scope *p){(void)p;}
static unsigned mock_layout=1;
static int mbx_inherited_service_fd(void){return 3;}
static int mock_ioctl(int fd,unsigned long op,void *out){(void)fd;if(op==MBX_WINDOW_LAYOUT){*(struct mbx_window_layout*)out=(struct mbx_window_layout){mock_layout,16,0x3fff,mock_layout==2?3U:0U,mock_layout==2?240U:0U,mock_layout==2?320U:0U,mock_layout==2?960U:0U,mock_layout==2?MBX_WINDOW_NATIVE_BYTES:MBX_WINDOW_LEGACY_BYTES};return 0;}if(op==MBX_WINDOW_BIND){assert(((struct mbx_window_request*)out)->destination==0);return 0;}assert(op==MBX_WINDOW_QUERY);*(struct mbx_window_token*)out=(struct mbx_window_token){7,11,0};return 0;}
#define ioctl mock_ioctl
#include "../mesa/mbx_window_cache.h"
#include "../mesa/mbx_window_export_impl.h"
int main(void){
 setenv("N810_MBX_DEVICE","1",1);setenv("N810_MBX_WINDOW_IMAGES","1",1);
 setenv("N810_MBX_WINDOW_FIRST","0",1);setenv("N810_MBX_WINDOW_COUNT","6",1);
 mbx_window_client_range(&client,3);assert(client.window_first==0&&client.window_count==6);
 assert(!mbx_window_range_valid(0,0)&&!mbx_window_range_valid(13,2)&&!mbx_window_range_valid(14,1));
 for(unsigned i=0;i<3;i++){
  resources[i].base=(struct pipe_resource){.target=1,.width0=128,.height0=128,.depth0=1,.array_size=1,.format=1,.reference={2}};
  resources[i].timestamp=10;images[i].pt=&resources[i].base;
  objects[i]=(struct gl_texture_object){.Target=1,.Image={{images+i}},.pt=&resources[i].base};
 }
 assert(mbx_window_choose(&client,&resources[0].base)==0);mbx_window_bind_target(&client,0);
 client.window[0].token=(struct mbx_window_token){7,11,0};client.window[0].timestamp=10;
 struct mbx_window_image image,bad;assert(!n810_mbx_window_export(1,&image));assert(mbx_window_image_valid(&image));
 assert(client.window[0].exported&&n810_mbx_window_export(1,&bad)==-EBUSY);
 assert(mbx_window_retire(&client)==-EBUSY);
 bad=image;bad.token.generation++;assert(n810_mbx_window_export_release(1,&bad)==-ESTALE&&client.window[0].exported);
 assert(!n810_mbx_window_export_release(1,&image)&&!client.window[0].exported);
 assert(!mbx_window_retire(&client));
 memset(&client,0,sizeof client);client.window_layout=1;client.window_first=6;client.window_count=8;assert(!mbx_window_claim(&client));
 struct sp_mbx_capture other={.window_first=6,.window_count=8};assert(mbx_window_claim(&other)==-EBUSY);
 other.window_first=0;other.window_count=6;assert(!mbx_window_claim(&other));assert(!mbx_window_retire(&other));
 for(unsigned i=0;i<10;i++){
  bad=image;
  if(i==0)bad.version++;if(i==1)bad.width--;if(i==2)bad.height--;if(i==3)bad.format++;
  if(i==4)bad.reserved=1;if(i==5)bad.token.session=0;if(i==6)bad.token.generation=0;
  if(i==7)bad.token.slot=14;if(i==8)bad.token.slot=15;if(i==9)bad.token.slot=UINT_MAX;
  assert(n810_mbx_window_import(2,&bad)==-EINVAL&&!client.window[0].resource);
 }
 bad=image;bad.token.session++;assert(n810_mbx_window_import(2,&bad)==-ESTALE);
 bad=image;bad.token.slot=6;assert(n810_mbx_window_import(2,&bad)==-EACCES);
 assert(!n810_mbx_window_import(2,&image));assert(client.window[0].resource==&resources[1].base&&client.window[0].imported);
 assert(resources[1].mbx_content.external_only&&client.window[0].timestamp==11);
 assert(n810_mbx_window_export(2,&bad)==-ENODATA);assert(n810_mbx_window_import(3,&image)==-EBUSY);
 client.header.magic=1;client.header.triangles=1;assert(n810_mbx_window_forget(2)==-EBUSY);
 client.rendered_count=1;assert(!n810_mbx_window_forget(2));assert(n810_mbx_window_forget(2)==-ENOENT);
 assert(resources[1].mbx_content.external_only);assert(!mbx_window_retire(&client));assert(!n810_mbx_transaction_begin()&&!n810_mbx_transaction_end());
 mock_layout=2;setenv("N810_MBX_WINDOW_FIRST","0",1);setenv("N810_MBX_WINDOW_COUNT","2",1);
 memset(&client,0,sizeof client);mbx_window_client_range(&client,3);assert(client.window_layout==2);
 resources[0].base.width0=240;resources[0].base.height0=320;assert(mbx_window_choose(&client,&resources[0].base)==0);
 client.window[0].token=(struct mbx_window_token){7,19,0};client.window[0].timestamp=resources[0].timestamp;
 assert(!n810_mbx_window_export(1,&image)&&image.version==2&&image.width==240&&image.height==320&&image.stride_bytes==960);
 bad=image;bad.version=1;bad.width=bad.height=128;bad.stride_bytes=0;assert(n810_mbx_window_export_release(1,&bad)==-EINVAL);
 assert(!n810_mbx_window_export_release(1,&image));assert(!mbx_window_retire(&client));
 memset(&client,0,sizeof client);client.window_layout=2;client.window_first=2;client.window_count=12;assert(!mbx_window_claim(&client));
 resources[1].base.width0=240;resources[1].base.height0=320;
 assert(!n810_mbx_window_import(2,&image));assert(!n810_mbx_window_forget(2));
 bad=image;bad.stride_bytes=1024;assert(n810_mbx_window_import(2,&bad)==-EINVAL);
 bad=image;bad.token.slot=2;assert(n810_mbx_window_import(2,&bad)==-EINVAL);
 struct mbx_window_layout caps;assert(!n810_mbx_window_get_layout(&caps)&&caps.version==2&&caps.native_mask==3);
 assert(!mbx_window_retire(&client));
 puts("window export/import: exact descriptor, pin/release, ranges, stale session, pending work and read-only invalidation passed");
}
