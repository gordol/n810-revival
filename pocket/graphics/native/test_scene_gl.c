/* SPDX-License-Identifier: GPL-2.0-or-later */
#define _POSIX_C_SOURCE 200809L
#define GL_GLEXT_PROTOTYPES
#define POCKET_SCENE_GL
#include <GL/osmesa.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>
static unsigned read_calls,upload_calls,draw_calls;
static void counted_read(GLint x,GLint y,GLsizei w,GLsizei h,GLenum f,GLenum t,void *p){++read_calls;glReadPixels(x,y,w,h,f,t,p);}
static void counted_upload(GLenum t,GLint l,GLint x,GLint y,GLsizei w,GLsizei h,GLenum f,GLenum ty,const void *p){++upload_calls;glTexSubImage2D(t,l,x,y,w,h,f,ty,p);}
static void counted_draw(GLenum mode,GLint first,GLsizei count){++draw_calls;glDrawArrays(mode,first,count);}
#define glReadPixels counted_read
#define glTexSubImage2D counted_upload
#define glDrawArrays counted_draw
struct window {unsigned width,height,stride;void *pixels;int leased;};
#include "present.h"
static int test_dma_fd=-1;
int pocket_window_dma_fd(void *ptr){(void)ptr;return test_dma_fd;}
int pocket_window_prepare(void *ptr,struct mbx_surface *p){struct window *w=ptr;if(!w->pixels||w->leased)return -1;*p=(struct mbx_surface){w->pixels,(size_t)w->stride*w->height,w->stride,w->width,w->height};return 0;}
int pocket_window_acquire(void *ptr,struct mbx_surface *p){struct window *w=ptr;if(!w->pixels||w->leased)return -1;w->leased=1;p->pixels=w->pixels;p->width=w->width;p->height=w->height;p->stride=w->stride;return 0;}
int pocket_window_submit(void *ptr){struct window *w=ptr;if(!w->leased)return -1;w->leased=0;return 0;}
static struct mbx_rect submitted_region;
int pocket_window_submit_region(void *ptr,unsigned x,unsigned y,unsigned width,unsigned height){submitted_region=(struct mbx_rect){x,y,width,height};return pocket_window_submit(ptr);}
int pocket_window_cancel(void *w){return pocket_window_submit(w);}
#include "gpu_scene.c"
#ifdef POCKET_TEST_ROOM_SCENE
#include "room_draw.h"
int pocket_room_set_eye_height(float);
int pocket_room_pixels_into(float,float,float,float,float,unsigned,unsigned,uint16_t *,unsigned,size_t,unsigned);
#endif
static void test_opaque_coverage(void){
 Scene_Vertex v[6]={0};const unsigned k[6]={0,1,2,0,2,3};
 for(unsigned i=0;i<6;i++)v[i].position=(Scene_FPoint){(k[i]==1||k[i]==2)?128:0,k[i]>=2?128:0};
 Scene_Texture t={0},source={0};t.stream=v;
 struct scene_command c={0};c.count=6;
 struct scene_gl_tile q={.w=128,.h=128};
 assert(scene_gl_covers(&t,&c,&q));
 c.blend=Scene_BLENDMODE_BLEND;assert(!scene_gl_covers(&t,&c,&q));c.blend=Scene_BLENDMODE_NONE;
 c.source=&source;source.blend=Scene_BLENDMODE_PREMULT;assert(!scene_gl_covers(&t,&c,&q));source.blend=Scene_BLENDMODE_NONE;
 c.clipped=1;c.clip=(Scene_Rect){0,0,127,128};assert(!scene_gl_covers(&t,&c,&q));c.clip.w=128;assert(scene_gl_covers(&t,&c,&q));
 v[3].position.x=1;assert(!scene_gl_covers(&t,&c,&q));v[3].position.x=0;
 q.x=1;assert(!scene_gl_covers(&t,&c,&q));q.x=0;c.count=3;assert(!scene_gl_covers(&t,&c,&q));
}
static void desktop_frame(void *s,int x,int partial){
 assert(!pocket_scene_begin_pixels(s,0x101018));
 if(partial)assert(!pocket_scene_damage(s,8,8,120,120));
 assert(!pocket_scene_rect(s,x+4,28,64,72,0x00000060));
 assert(!pocket_scene_rect(s,x,24,64,72,0x987654a0));
 assert(!pocket_scene_rect(s,55,40,40,40,0x1256abc0));
 assert(!pocket_scene_rect(s,420,180,70,65,0xabcdef80));
}
static void test_desktop_damage(void){
 setenv("POCKET_SCENE_OPAQUE_TARGETS","1",1);setenv("POCKET_SCENE_OUTPUT_TILE","400x256",1);
 uint16_t backing[400*400];OSMesaContext gl=OSMesaCreateContextExt(OSMESA_RGB_565,24,0,0,NULL);assert(gl);assert(OSMesaMakeCurrent(gl,backing,GL_UNSIGNED_SHORT_5_6_5,400,400));
 enum {W=800,H=480,N=W*H};uint16_t *guard=malloc((N+64)*2),*reference=malloc(N*2);assert(guard&&reference);
 for(unsigned i=0;i<N+64;i++)guard[i]=0xa55a;
 struct window w={W,H,W*2,guard+32,0};void *s=pocket_scene_open(&w,0);assert(s);assert(!pocket_scene_size(s,W,H));
 desktop_frame(s,16,0);assert(!pocket_scene_present(s,0));
 unsigned before=read_calls;desktop_frame(s,32,1);assert(!pocket_scene_present(s,0));unsigned partial=read_calls-before;
 assert(submitted_region.x==8&&submitted_region.y==8&&submitted_region.width==120&&submitted_region.height==120);
 desktop_frame(s,32,0);assert(!pocket_scene_capture(s,reference,N*2));assert(!memcmp(reference,w.pixels,N*2));
 assert(partial==1); /* One affected400x256tile, including old+new shadow. */
 for(unsigned i=0;i<32;i++){assert(guard[i]==0xa55a);assert(guard[N+32+i]==0xa55a);}
 /* A changed destination has no retained content: force a complete frame. */
 memset(reference,0,N*2);w.pixels=reference;before=read_calls;
 desktop_frame(s,32,1);assert(!pocket_scene_present(s,0));assert(read_calls-before==4);assert(!memcmp(reference,guard+32,N*2));
 assert(pocket_scene_damage(s,-1,0,1,1)<0);assert(pocket_scene_damage(s,801,0,1,1)<0);
 /* Retain an immutable window command batch, replay without repacking,
  * and keep its source references alive even after the owner drops it. */
 assert(!pocket_scene_begin_pixels(s,0x101018));assert(!pocket_scene_batch_begin(s));
 assert(pocket_scene_batch_begin(s)<0);
 assert(!pocket_scene_rect(s,24,32,140,80,0x123456c0));
 assert(!pocket_scene_rect(s,60,45,80,70,0x987654a0));
 void *batch=pocket_scene_batch_end(s);assert(batch);
 assert(((struct gpu_scene*)s)->canvas->vertices==0);
 assert(!pocket_scene_batch_replay(s,batch));assert(((struct gpu_scene*)s)->canvas->vertices==(((struct scene_texture *)batch)->image_cache?((struct scene_texture *)batch)->texture->n*6:0));
 assert(!pocket_scene_present(s,0));
 assert(!pocket_scene_begin_pixels(s,0x101018));assert(!pocket_scene_batch_replay(s,batch));
 pocket_scene_texture_free(batch);assert(!pocket_scene_capture(s,guard+32,N*2));assert(!memcmp(reference,guard+32,N*2));
 assert(!pocket_scene_begin_pixels(s,0x101018));assert(!pocket_scene_rect(s,24,32,140,80,0x123456c0));assert(!pocket_scene_rect(s,60,45,80,70,0x987654a0));
 assert(!pocket_scene_capture(s,guard+32,N*2));
 if(memcmp(reference,guard+32,N*2)){unsigned differences=0,maxr=0,maxg=0,maxb=0;for(unsigned k=0;k<N;k++){unsigned a=reference[k],b=guard[k+32];if(a!=b)differences++;unsigned dr=abs((int)(a>>11)-(int)(b>>11)),dg=abs((int)((a>>5)&63)-(int)((b>>5)&63)),db=abs((int)(a&31)-(int)(b&31));if(dr>maxr)maxr=dr;if(dg>maxg)maxg=dg;if(db>maxb)maxb=db;}fprintf(stderr,"window image differential pixels=%u max_rgb565=%u,%u,%u\n",differences,maxr,maxg,maxb);}
 if(getenv("POCKET_SCENE_WINDOW_IMAGES"))for(unsigned k=0;k<N;k++){
  unsigned a=reference[k],b=guard[k+32];assert((a==0x1083)==(b==0x1083));
  assert(abs((int)(a>>11)-(int)(b>>11))<=1);assert(abs((int)((a>>5)&63)-(int)((b>>5)&63))<=1);assert(abs((int)(a&31)-(int)(b&31))<=1);
 }else assert(!memcmp(reference,guard+32,N*2));
 assert(!pocket_scene_batch_begin(s));assert(!pocket_scene_rect(s,0,0,1,1,0xff0000ff));assert(!pocket_scene_batch_abort(s));assert(((struct gpu_scene*)s)->canvas->count==0);
 /* Placement changes leave the captured vertices immutable; GPU transforms
  * and translated clips must match rebuilding at the final coordinates. */
 assert(!pocket_scene_begin_pixels(s,0x101018));assert(!pocket_scene_batch_begin(s));
 assert(!pocket_scene_rect(s,24,32,140,80,0x123456c0));
 assert(!pocket_scene_rect(s,60,45,80,70,0x987654a0));
 batch=pocket_scene_batch_end(s);assert(batch);
 {struct gpu_scene *owner=s;Scene_Renderer *renderer=owner->device;
  Scene_Texture *captured=((struct scene_texture *)batch)->texture;
  assert(captured->bounds_valid);unsigned old_first=renderer->tile_first,old_end=renderer->tile_end;renderer->tile_first=0;renderer->tile_end=owner->canvas->n;int old_cull=renderer->damage_cull;renderer->damage_cull=1;int old_dma_damage=renderer->dma_damage;Scene_Rect previous=owner->canvas->damage;int valid=owner->canvas->damage_valid;
  renderer->sink_dma=renderer->dma_damage=1;owner->canvas->damage_valid=1;owner->canvas->damage=(Scene_Rect){600,350,50,50};
  uint64_t culled=renderer->damage_culled_batches;
  assert(!scene_gl_geometry_now(renderer,captured,NULL,0,NULL,0,NULL));assert(renderer->damage_culled_batches==culled+1);
  owner->canvas->damage=(Scene_Rect){20,30,200,100};unsigned before_draws=draw_calls;
  assert(!scene_gl_geometry_now(renderer,captured,NULL,0,NULL,0,NULL));assert(draw_calls>before_draws);assert(renderer->damage_culled_batches==culled+1);
  renderer->translate_x=600;renderer->translate_y=400;
  assert(!scene_gl_geometry_now(renderer,captured,NULL,0,NULL,0,NULL));assert(renderer->damage_culled_batches==culled+2);
  renderer->translate_x=renderer->translate_y=0;
  captured->commands[0].dx=1;scene_recorded_bounds(captured);assert(!captured->bounds_valid);
  captured->commands[0].dx=0;scene_recorded_bounds(captured);assert(captured->bounds_valid);
  float x=captured->stream[0].position.x;captured->stream[0].position.x=NAN;scene_recorded_bounds(captured);assert(!captured->bounds_valid);
  captured->stream[0].position.x=x;scene_recorded_bounds(captured);assert(captured->bounds_valid);
  renderer->tile_first=old_first;renderer->tile_end=old_end;renderer->sink_dma=0;renderer->damage_cull=old_cull;renderer->dma_damage=old_dma_damage;owner->canvas->damage_valid=valid;owner->canvas->damage=previous;
 }
 if(getenv("POCKET_SCENE_WINDOW_IMAGES")){
  for(unsigned reuse=0;reuse<9;reuse++){
   assert(!pocket_scene_begin_pixels(s,0x101018));assert(!pocket_scene_batch_replay(s,batch));
   assert(((struct scene_texture *)batch)->image_cache==(reuse==8));
   assert(!pocket_scene_capture(s,reference,N*2));
  }
 }
 const int moves[][2]={{0,0},{390,210},{-35,-40},{700,420},{-100,12}};
 for(unsigned m=0;m<sizeof moves/sizeof moves[0];m++){
  int dx=moves[m][0],dy=moves[m][1];
  assert(!pocket_scene_begin_pixels(s,0x101018));assert(!pocket_scene_batch_replay_offset(s,batch,dx,dy));
  assert(!pocket_scene_capture(s,reference,N*2));
  assert(!pocket_scene_begin_pixels(s,0x101018));
  assert(!pocket_scene_rect(s,24+dx,32+dy,140,80,0x123456c0));
  assert(!pocket_scene_rect(s,60+dx,45+dy,80,70,0x987654a0));
  assert(!pocket_scene_capture(s,guard+32,N*2));
  unsigned diff=0,first=0;for(unsigned k=0;k<N;k++)if(reference[k]!=guard[k+32]){if(!diff)first=k;diff++;}
  if(diff)fprintf(stderr,"translated mismatch move=%u dx=%d dy=%d pixels=%u first=%u,%u values=%x,%x\n",m,dx,dy,diff,first%W,first/W,reference[first],guard[first+32]);
  if(diff)for(unsigned k=0;k<N;k++){
   unsigned a=reference[k],b=guard[k+32];
   /* Matrix association may round a blended channel by one native RGB565
    * step. Preserve silhouette and reject larger color/coverage differences. */
   assert((a==0x1083)==(b==0x1083));
   assert(abs((int)(a>>11)-(int)(b>>11))<=1);
   assert(abs((int)((a>>5)&63)-(int)((b>>5)&63))<=1);
   assert(abs((int)(a&31)-(int)(b&31))<=1);
  }
 }
 pocket_scene_texture_free(batch);
 uint32_t ids[]={0,99,2901,2999},bounds[4];
 assert(!pocket_scene_index_bounds(ids,4,100,30,bounds));assert(bounds[0]==0&&bounds[1]==0&&bounds[2]==100&&bounds[3]==30);
 assert(!pocket_scene_index_bounds(NULL,0,100,30,bounds));assert(!bounds[2]&&!bounds[3]);
 ids[0]=3000;assert(pocket_scene_index_bounds(ids,4,100,30,bounds)<0);
 puts("translated_geometry compared_pixels=1920000 max_rgb565_channel_rounding=1 geometry_rebuilds=0 damage_bounds=validated");
 puts(getenv("POCKET_SCENE_WINDOW_IMAGES")?"retained_images replay_pixels=384000 exact_replay=1 direct_max_rgb565_step=1 lifetime=clean":"retained_commands exact_pixels=384000 replay_vertex_copies=0 lifetime=clean partial_submit=120x120");
 /* Sparse PNW artwork must agree with the established dense glyph renderer,
  * including solid half blocks, irregular glyphs, and replacing overlays. */
 uint32_t codes[3]={32,65,0x2584};unsigned char bits[48]={0};
 for(unsigned y=0;y<16;y++){bits[16+y]=(unsigned char)(y*17+9);bits[32+y]=y>=8?255:0;}
 assert(!pocket_scene_font(s,codes,bits,3,NULL,NULL,0));
 uint32_t palette[16]={0};struct scene_mark base[32],overlay[3];struct scene_cell_record dense[32];
 for(unsigned i=0;i<32;i++){
  uint64_t ink=(UINT64_C(1)<<48)|((uint64_t)(0x357a92+i*7)<<24)|(0x182833+i*19);
  base[i]=(struct scene_mark){i,0x2584,ink};dense[i]=(struct scene_cell_record){i,0x2584,ink};
 }
 for(unsigned i=0;i<3;i++){unsigned at=i*7+2;overlay[i]=(struct scene_mark){at,65,(UINT64_C(1)<<48)|(UINT64_C(0xa17556)<<24)|0x182833};dense[at]=(struct scene_cell_record){at,65,overlay[i].ink};}
 assert(!pocket_scene_begin_pixels(s,0x101018));
 assert(!pocket_scene_landscape(s,base,32,8,4,24,32,palette,16,0));
 assert(!pocket_scene_landscape(s,overlay,3,8,4,24,32,palette,16,0));
 assert(!pocket_scene_present(s,0));
 assert(!pocket_scene_begin_pixels(s,0x101018));
 assert(!pocket_scene_window_draw(s,dense,8,4,24,32,palette,16,0,1,255));
 assert(!pocket_scene_capture(s,guard+32,N*2));assert(!memcmp(reference,guard+32,N*2));
 puts("PNW_sparse_native_artwork exact_pixels=384000 half_blocks_and_overlays=equal");
 /* Forward final target matches the conventional bottom-up output exactly. */
 assert(!pocket_scene_begin_pixels(s,0x101018));
 assert(!pocket_scene_window_draw(s,dense,8,4,24,32,palette,16,0,1,255));
 struct gpu_scene *gs=s;gs->device->sink_forward=1;assert(!scene_gl_flush(gs->device,gs->canvas));
 for(unsigned ti=0;ti<gs->canvas->n;ti++){
  struct scene_gl_tile *q=gs->canvas->tiles+ti;uint16_t *tile=malloc(q->pw*q->ph*2);assert(tile);
  scene_gl_bind(gs->device,q->fbo);glPixelStorei(GL_PACK_ALIGNMENT,1);glReadPixels(0,0,q->pw,q->ph,GL_RGB,GL_UNSIGNED_SHORT_5_6_5,tile);
  for(unsigned y=0;y<q->h;y++)memcpy(guard+32+(q->y+y)*W+q->x,tile+y*q->pw,q->w*2);
  free(tile);
 }
 gs->device->sink_forward=0;assert(!memcmp(reference,guard+32,N*2));
 puts("forward_output exact_pixels=384000 glyphs=equal padding_rows=excluded");
 pocket_scene_close(s);free(reference);free(guard);OSMesaDestroyContext(gl);
 puts("desktop_damage exact_pixels=384000 retained_tiles=3 redrawn_tiles=1 guards=clean changed_destination=full_redraw");
}
static void test_wide_target(void){
 setenv("POCKET_SCENE_OPAQUE_TARGETS","1",1);
 uint16_t backing[400*400];OSMesaContext gl=OSMesaCreateContextExt(OSMESA_RGB_565,24,0,0,NULL);assert(gl);assert(OSMesaMakeCurrent(gl,backing,GL_UNSIGNED_SHORT_5_6_5,400,400));
 struct window w={0};void *s=pocket_scene_open(&w,0);assert(s);
 uint32_t codes[130];unsigned char bits[130*16];for(unsigned i=0;i<130;i++){codes[i]=32+i;for(unsigned y=0;y<16;y++)bits[i*16+y]=i?(unsigned char)(i*13+y*17):0;}
 assert(!pocket_scene_font(s,codes,bits,130,NULL,NULL,0));
 uint16_t *a=malloc(768000),*b=malloc(768000);assert(a&&b);
 for(unsigned pass=0;pass<2;pass++){
  assert(!setenv("POCKET_SCENE_OUTPUT_TILE",pass?"800x480":"400x256",1));assert(!pocket_scene_size(s,16,16));assert(!pocket_scene_size(s,800,480));
  desktop_frame(s,32,0);assert(!pocket_scene_rect(s,0,0,16,16,0xff0000ff));assert(!pocket_scene_rect(s,784,464,16,16,0x00ff00ff));
  uint32_t label[]={80,111,99,107,101,116};assert(!pocket_scene_text(s,500,450,label,6,0xffffff));
  assert(!pocket_scene_capture(s,pass?b:a,768000));
 }
 assert(!memcmp(a,b,768000));free(a);free(b);pocket_scene_close(s);OSMesaDestroyContext(gl);
 puts("single_target exact_pixels=384000 tiled_reference=400x256 candidate=800x480 text_and_alpha=equal");
}
static void test_page_groups(void){
 setenv("POCKET_SCENE_OPAQUE_TARGETS","1",1);setenv("POCKET_SCENE_COMPILED","1",1);
 unsetenv("POCKET_SCENE_WINDOW_IMAGES");
 uint16_t backing[64*64];OSMesaContext gl=OSMesaCreateContextExt(OSMESA_RGB_565,24,0,0,NULL);assert(gl);assert(OSMesaMakeCurrent(gl,backing,GL_UNSIGNED_SHORT_5_6_5,64,64));
 struct window w={0};void *s=pocket_scene_open(&w,0);assert(s);assert(!pocket_scene_size(s,800,480));
 uint32_t codes[260];unsigned char bits[260*16];for(unsigned i=0;i<260;i++){codes[i]=32+i;for(unsigned y=0;y<16;y++)bits[i*16+y]=(unsigned char)(i*13+y*17);}
 assert(!pocket_scene_font(s,codes,bits,260,NULL,NULL,0));
 uint16_t *reference=malloc(768000),*pixels=malloc(768000);assert(reference&&pixels);
 unsigned groups=0;uint64_t candidates[2]={0};
 for(unsigned mode=0;mode<3;mode++)for(unsigned pass=0;pass<2;pass++){
  setenv("POCKET_SCENE_PAGE_GROUPS",pass?"1":"0",1);
  assert(!pocket_scene_begin_pixels(s,0x101018));assert(!pocket_scene_rect(s,16,16,600,320,0x736b59ff));
  assert(!pocket_scene_batch_begin(s));
  struct gpu_scene *owner=s;Scene_Rect clip={20,20,440,240};if(mode==1)assert(!Scene_RenderSetClipRect(owner->device,&clip));
  for(unsigned row=0;row<8;row++){
   uint32_t text[64];for(unsigned col=0;col<64;col++)text[col]=codes[(col*129+row*37)%260];
   assert(!pocket_scene_text(s,12,24+row*15,text,64,0xffffff-(row*0x102030)));
  }
  assert(!Scene_RenderSetClipRect(owner->device,NULL));
  void *batch=pocket_scene_batch_end(s);assert(batch);assert(!pocket_scene_batch_replay_offset(s,batch,mode==2?37:0,mode==2?-13:0));
  uint64_t before_candidates=owner->device->page_candidates;
  assert(!pocket_scene_capture(s,pass?pixels:reference,768000));
  candidates[pass]+=owner->device->page_candidates-before_candidates;
  Scene_Texture *recorded=((struct scene_texture *)batch)->texture;
  for(size_t j=0;j<recorded->count;j++){
   struct scene_command *c=recorded->commands+j;struct scene_geometry *g=c->compiled;
   if(!g||!c->source||c->source->n<2)continue;
   assert((g->page_offsets!=NULL)==(pass!=0));
   if(pass)for(unsigned page=0;page<c->source->n;page++){
    unsigned previous=0;
    for(unsigned k=g->page_offsets[page];k<g->page_offsets[page+1];k++){
     unsigned id=g->page_primitives[k];assert(id<g->vertices/3);assert(g->primitive[id].page==(int)page);
     if(k>g->page_offsets[page])assert(previous<id);previous=id;++groups;
    }
   }
  }
  pocket_scene_texture_free(batch);
  if(pass)assert(!memcmp(reference,pixels,768000));
 }
 assert(groups>0&&candidates[1]<candidates[0]);free(reference);free(pixels);pocket_scene_close(s);OSMesaDestroyContext(gl);
 printf("atlas_page_groups cases=3 exact_pixels=1152000 stable_primitive_memberships=%u scratch_vertex_copies=0 page_candidates_before=%llu after=%llu\n",groups,(unsigned long long)candidates[0],(unsigned long long)candidates[1]);
}
int main(int argc,char **argv){
 test_opaque_coverage();
 if(argc==2&&!strcmp(argv[1],"--page-reference")){test_page_groups();return 0;}
 if(argc==2&&!strcmp(argv[1],"--wide-reference")){test_wide_target();return 0;}
 if(argc==2&&!strcmp(argv[1],"--desktop-reference")){test_desktop_damage();return 0;}
 int prepared_reference=argc==2&&!strcmp(argv[1],"--prepared-reference");
 int prepared_only=prepared_reference||(argc==2&&!strcmp(argv[1],"--prepared-hardware"));
 int dma_only=argc==2&&!strcmp(argv[1],"--dma-hardware");
 int owned_only=dma_only||(argc==2&&!strcmp(argv[1],"--owned-hardware"));
 int pixel_only=argc==2&&!strcmp(argv[1],"--pixel-hardware");
 int hardware=argc==2&&(!strcmp(argv[1],"--hardware")||pixel_only||owned_only||(prepared_only&&!prepared_reference));assert(argc==1||hardware||prepared_reference);
 uint16_t backing[400*400];OSMesaContext gl=OSMesaCreateContextExt(OSMESA_RGB_565,24,0,0,NULL);assert(gl);assert(OSMesaMakeCurrent(gl,backing,GL_UNSIGNED_SHORT_5_6_5,400,400));
 int window_proof=getenv("POCKET_WINDOW_PROOF")!=NULL;if(window_proof)unsetenv("POCKET_SCENE_WINDOW_IMAGES");
 int text_proof=getenv("POCKET_TEXT_PROOF")!=NULL;if(text_proof)unsetenv("POCKET_SCENE_TEXT_RUNS");
 struct window w={0};void *s=pocket_scene_open(&w,hardware);assert(s);unsigned width=520,height=272,cols=65,rows=17;
 assert(!pocket_scene_size(s,width,height));uint32_t codes[130];unsigned char bits[130*16];for(unsigned i=0;i<130;i++){codes[i]=32+i;for(unsigned y=0;y<16;y++)bits[i*16+y]=i?(unsigned char)(i*13+y*17):0;}assert(!pocket_scene_font(s,codes,bits,130,NULL,NULL,0));
 if(pixel_only||owned_only){
  assert(!pocket_scene_size(s,800,480));assert(!pocket_scene_begin_pixels(s,0x101018));if(!dma_only)assert(!pocket_scene_flux_pixels(s,12,1,.15,2));
  if(window_proof)assert(!pocket_scene_batch_begin(s));
  assert(!pocket_scene_rect(s,80,48,window_proof?140:640,window_proof?80:320,0x202020c0));uint32_t label[]={80,111,99,107,101,116};assert(!pocket_scene_text(s,88,56,label,6,0xffffff));
  if(window_proof){void *batch=pocket_scene_batch_end(s);assert(batch);assert(!pocket_scene_batch_replay(s,batch));pocket_scene_texture_free(batch);}
  uint16_t *frame=malloc(800*480*2);assert(frame);assert(!pocket_scene_capture(s,frame,800*480*2));
  if(owned_only){
   if(window_proof)setenv("POCKET_SCENE_WINDOW_IMAGES","1",1);
   if(text_proof){setenv("POCKET_SCENE_TEXT_RUNS","1",1);assert(!pocket_scene_font(s,codes,bits,130,NULL,NULL,0));}
   uint16_t *guard=malloc((800*480+64)*2);assert(guard);for(unsigned i=0;i<800*480+64;i++)guard[i]=0xa55a;
   w.width=800;w.height=480;w.stride=1600;w.pixels=guard+32;
   if(dma_only){const char *fd=getenv("NATIVE_FB_FD");assert(fd);test_dma_fd=atoi(fd);assert(test_dma_fd>=3);
    w.pixels=mmap(NULL,768000,PROT_READ|PROT_WRITE,MAP_SHARED,test_dma_fd,0);assert(w.pixels!=MAP_FAILED);
   }
   if(getenv("POCKET_WIDE_PROOF")){assert(!setenv("POCKET_SCENE_OUTPUT_TILE","800x480",1));assert(!pocket_scene_size(s,16,16));assert(!pocket_scene_size(s,800,480));}
   assert(!pocket_scene_begin_pixels(s,0x101018));if(!dma_only)assert(!pocket_scene_flux_pixels(s,12,1,.15,2));
   if(window_proof)assert(!pocket_scene_batch_begin(s));
   assert(!pocket_scene_rect(s,80,48,window_proof?140:640,window_proof?80:320,0x202020c0));assert(!pocket_scene_text(s,88,56,label,6,0xffffff));
   if(window_proof){void *batch=pocket_scene_batch_end(s);assert(batch);setenv("POCKET_SCENE_WINDOW_WARMUP","0",1);assert(!pocket_scene_batch_replay(s,batch));assert(((struct scene_texture *)batch)->image_cache);pocket_scene_texture_free(batch);}
   unsigned long long driver_reads_before=0;
   if(window_proof){FILE *f=fopen("/sys/module/n810_mbx_gpu_probe/parameters/gpu_read_bytes","r");assert(f&&fscanf(f,"%llu",&driver_reads_before)==1);fclose(f);}
   unsigned reads_before=read_calls;setenv(dma_only?"POCKET_DMA_SINK":"POCKET_OWNED_SINK","1",1);
   assert(!pocket_scene_present(s,0));assert(read_calls==reads_before);
   if(window_proof){unsigned long long after;FILE *f=fopen("/sys/module/n810_mbx_gpu_probe/parameters/gpu_read_bytes","r");assert(f&&fscanf(f,"%llu",&after)==1);fclose(f);assert(after==driver_reads_before);puts("WINDOW_IMAGE_PROOF driver_readback_bytes=0");}
   if(memcmp(frame,w.pixels,768000)){
    unsigned diff=0,first=0;for(unsigned k=0;k<384000;k++)if(frame[k]!=((uint16_t*)w.pixels)[k]){if(!diff)first=k;diff++;}
    fprintf(stderr,"DMA mismatch pixels=%u first=%u,%u reference=%04x actual=%04x\n",diff,first%800,first/800,frame[first],((uint16_t*)w.pixels)[first]);
    const char *dir=getenv("POCKET_PROOF_DIR");if(dir){char name[512];snprintf(name,sizeof(name),"%s/dma-reference.rgb565",dir);FILE *f=fopen(name,"wb");assert(f);assert(fwrite(frame,1,768000,f)==768000);fclose(f);snprintf(name,sizeof(name),"%s/dma-actual.rgb565",dir);f=fopen(name,"wb");assert(f);assert(fwrite(w.pixels,1,768000,f)==768000);fclose(f);}
   }
   if(window_proof){unsigned changed=0,maxstep=0;for(unsigned k=0;k<384000;k++){
    unsigned a=frame[k],b=((uint16_t*)w.pixels)[k];if(a!=b)changed++;
    for(unsigned c=0;c<3;c++){unsigned shift=c==0?11:c==1?5:0,mask=c==1?63:31;unsigned d=abs((int)((a>>shift)&mask)-(int)((b>>shift)&mask));assert(d<=1);if(d>maxstep)maxstep=d;}
    assert((a==frame[0])==(b==frame[0]));
   }printf("WINDOW_IMAGE_PROOF pixels=384000 changed=%u max_rgb565_step=%u coverage=exact\n",changed,maxstep);
   }else assert(!memcmp(frame,w.pixels,768000));
   for(unsigned i=0;i<32;i++){assert(guard[i]==0xa55a);assert(guard[800*480+32+i]==0xa55a);}
   uint64_t stats[2];assert(!(dma_only?pocket_scene_dma_stats(s,stats):pocket_scene_sink_stats(s,stats)));assert(stats[0]==(getenv("POCKET_WIDE_PROOF")?1U:4U)&&stats[1]==768000);
   if(dma_only){assert(!pocket_scene_sink_stats(s,stats));assert(!stats[0]&&!stats[1]);puts(window_proof?"DMA window_proof_pixels=384000 glReadPixels=0 CPU_sink_bytes=0 DMA_bytes=768000":"DMA exact_pixels=384000 glReadPixels=0 CPU_sink_bytes=0 DMA_bytes=768000");munmap(w.pixels,768000);}
   if(!dma_only)puts("owned_surface exact_pixels=384000 guards=clean glReadPixels=0 explicit_CPU_sink_bytes=768000");
   unsetenv("POCKET_OWNED_SINK");unsetenv("POCKET_DMA_SINK");free(guard);w.pixels=NULL;
  }
  free(frame);pocket_scene_close(s);OSMesaDestroyContext(gl);puts("native_pixel_full_scene_complete");return 0;
 }
 uint32_t cells[65*17*2];for(unsigned i=0;i<cols*rows;i++){cells[2*i]=32+i%130;cells[2*i+1]=0x001ff800;}
 assert(!pocket_scene_cells(s,cells,cols,rows,0));assert(!pocket_scene_begin(s));assert(!read_calls);uint16_t *allocation=malloc((width*height+64)*2);assert(allocation);for(unsigned i=0;i<width*height+64;i++)allocation[i]=0xa55a;uint16_t *pixels=allocation+32;assert(!pocket_scene_capture(s,pixels,width*height*2));unsigned bad=0;
 for(unsigned y=0;y<height;y++)for(unsigned x=0;x<width;x++){unsigned i=y/16*cols+x/8;uint16_t expected=(bits[(cells[i*2]-32)*16+y%16]&(128>>(x%8)))?0xf800:0x001f;if(pixels[y*width+x]!=expected)bad++;}
 printf("shared_GL_scene pixels=%u mismatches=%u tiled_targets=15 draw_batches=%u\n",width*height,bad,draw_calls);fflush(stdout);assert(!bad);
 /* The pixel API does not call the cell encoder or allocate a cell plane. */
 assert(!pocket_scene_begin_pixels(s,0x0000ff));
 assert(!pocket_scene_rect(s,0,0,16,16,0xff0000ff));
 uint32_t label=codes[1];assert(!pocket_scene_text(s,24,0,&label,1,0x00ff00));
 assert(!pocket_scene_capture(s,pixels,width*height*2));
 for(unsigned y=0;y<height;y++)for(unsigned x=0;x<width;x++){
  uint16_t expected=x<16&&y<16?0xf800:0x001f;
  if(x>=24&&x<32&&y<16&&(bits[16+y]&(128>>(x-24))))expected=0x07e0;
  assert(pixels[y*width+x]==expected);
 }
 printf("shared_native_pixels rectangles_and_text_exact=1 cell_plane_used=0\n");fflush(stdout);
 if(prepared_only){
  for(unsigned repeat=0;repeat<8;++repeat){
   assert(!pocket_scene_begin_pixels(s,0x0000ff));
   assert(!pocket_scene_rect(s,0,0,16,16,0xff0000ff));
   assert(!pocket_scene_text(s,24,0,&label,1,0x00ff00));
   assert(!pocket_scene_capture(s,pixels,width*height*2));
   for(unsigned y=0;y<height;y++)for(unsigned x=0;x<width;x++){
    uint16_t expected=x<16&&y<16?0xf800:0x001f;
    if(x>=24&&x<32&&y<16&&(bits[16+y]&(128>>(x-24))))expected=0x07e0;
    assert(pixels[y*width+x]==expected);
   }
   for(unsigned i=0;i<32;++i){assert(allocation[i]==0xa55a);assert(allocation[width*height+32+i]==0xa55a);}
  }
  FILE *f=fopen("prepared-scene.rgb565","wb");assert(f);assert(fwrite(pixels,2,width*height,f)==width*height);assert(!fclose(f));
  printf("prepared_native_pixels exact_pixels_per_frame=%u repeated_frames=8 guards=clean\n",width*height);
  free(allocation);pocket_scene_close(s);OSMesaDestroyContext(gl);return 0;
 }

 uint16_t *flux_reference=malloc(width*height*2);assert(flux_reference);
 assert(!pocket_scene_begin_pixels(s,0x101018));assert(!pocket_scene_flux_pixels(s,12,1,.15,2));assert(!pocket_scene_capture(s,flux_reference,width*height*2));
 assert(!pocket_scene_begin_pixels(s,0x101018));assert(!pocket_scene_flux_pixels(s,12,1,.15,2));assert(!pocket_scene_capture(s,pixels,width*height*2));assert(!memcmp(pixels,flux_reference,width*height*2));
 unsigned flux_changed=0;for(unsigned i=0;i<width*height;i++)if(pixels[i]!=pixels[0])flux_changed++;assert(flux_changed>100);
 assert(pocket_scene_flux_pixels(s,12,5,.15,2)<0);assert(pocket_scene_flux_pixels(s,NAN,1,.15,2)<0);
 printf("shared_native_flux deterministic=1 changed_pixels=%u cell_plane_used=0\n",flux_changed);fflush(stdout);free(flux_reference);

 #ifdef POCKET_TEST_ROOM_SCENE
 uint16_t *reference=malloc(width*height*2);assert(reference);glBindFramebuffer(GL_FRAMEBUFFER,0);assert(!setenv("POCKET_GL_TARGET","direct",1));glDisable(GL_SCISSOR_TEST);
 assert(pocket_room_pixels_into(.75f,20,0,.08f,.03f,width,height,reference,width,width*height*2,400)>0);
 assert(!pocket_scene_room_source(s,pocket_room_draw_tile,pocket_room_set_eye_height));
 int direct=getenv("POCKET_SCENE_DIRECT_ROOM")&&!strcmp(getenv("POCKET_SCENE_DIRECT_ROOM"),"1");
 if(direct)assert(!pocket_scene_room_region_source(s,pocket_room_draw_region));
 void *room=pocket_scene_room_create(s,width,height);assert(room);
 unsigned reads_before=read_calls,uploads_before=upload_calls;
 assert(pocket_scene_room(s,room,.75f,20,0,.08f,.03f,340)>0);
 /* Explicit diagnostic read of the source isolates composition precision
  * from the different viewport offsets of the old 400px tile renderer. */
 uint16_t *source_pixels=malloc(width*height*2);assert(source_pixels);
 struct gpu_scene *gs=s;struct scene_texture *room_image=room;
 if(direct)assert(!room_image->texture->n&&!room_image->texture->tiles);
 if(!direct){assert(!Scene_SetRenderTarget(gs->device,room_image->texture));
 assert(!Scene_RenderReadPixels(gs->device,NULL,Scene_PIXELFORMAT_RGB565,source_pixels,width*2));}else memcpy(source_pixels,reference,width*height*2);
 reads_before=read_calls;
 /* A new desktop frame starts after the independent atlas capture. */
 assert(!pocket_scene_begin(s));assert(!pocket_scene_image(s,room,0,0));assert(read_calls==reads_before&&upload_calls==uploads_before);
 assert(!pocket_scene_capture(s,pixels,width*height*2));bad=0;
 for(unsigned i=0;i<width*height;i++)if(pixels[i]!=reference[i]){if(bad<64)fprintf(stderr,"ROOM_PIXEL x=%u y=%u reference=%04x scene=%04x\n",i%width,i/width,reference[i],pixels[i]);bad++;}
 if(hardware){FILE *f=fopen("room-reference.rgb565","wb");assert(f);assert(fwrite(reference,2,width*height,f)==width*height);assert(!fclose(f));f=fopen("room-scene.rgb565","wb");assert(f);assert(fwrite(pixels,2,width*height,f)==width*height);assert(!fclose(f));}
 unsigned max_delta=0,composition_bad=0;
 for(unsigned i=0;i<width*height;i++){
  if(pixels[i]!=source_pixels[i])composition_bad++;
  for(unsigned k=0;k<3;k++){unsigned shift=k==0?11:k==1?5:0,mask=k==1?63:31;int d=(int)((reference[i]>>shift)&mask)-(int)((pixels[i]>>shift)&mask);unsigned delta=d<0?-d:d;if(delta>max_delta)max_delta=delta;}
 }
 printf("shared_Room_scene pixels=%u reference_different_pixels=%u maximum_RGB565_channel_delta=%u direct_geometry=%u",width*height,bad,max_delta,direct);if(!direct)printf(" source_composition_mismatches=%u",composition_bad);printf(" frontend_intermediate_readbacks=0 pixel_uploads=0\n");fflush(stdout);assert((direct||!composition_bad)&&max_delta<=1);assert(!pocket_scene_begin(s));assert(!pocket_scene_image(s,room,16,16));assert(!pocket_scene_capture(s,pixels,width*height*2));
 unsigned partial_bad=0;
 for(unsigned y=0;y<height;y++)for(unsigned x=0;x<width;x++){
  unsigned i=y/16*cols+x/8;uint16_t expected=(bits[(cells[i*2]-32)*16+y%16]&(128>>(x%8)))?0xf800:0x001f;
  if(x>=16&&y>=16)expected=source_pixels[(y-16)*width+x-16];
  if(pixels[y*width+x]!=expected){
   unsigned delta=0;for(unsigned k=0;k<3;k++){unsigned shift=k==0?11:k==1?5:0,mask=k==1?63:31;int d=(int)((expected>>shift)&mask)-(int)((pixels[y*width+x]>>shift)&mask);unsigned v=d<0?-d:d;if(v>delta)delta=v;}
   if(!direct||delta>1)partial_bad++;
  }
 }
 printf("shared_partial_Room pixels=%u pixels_beyond_tolerance=%u tolerance_RGB565_channel_steps=%u\n",width*height,partial_bad,direct?1:0);fflush(stdout);assert(!partial_bad);
 assert(!pocket_scene_begin(s));assert(!pocket_scene_image(s,room,16,16));
 assert(!Scene_SetRenderDrawColor(gs->device,255,0,0,128));assert(!Scene_SetRenderDrawBlendMode(gs->device,Scene_BLENDMODE_BLEND));
 Scene_Rect overlay={32,32,64,32};assert(!Scene_RenderFillRect(gs->device,&overlay));assert(!pocket_scene_capture(s,pixels,width*height*2));
 unsigned alpha_bad=0;
 for(unsigned y=32;y<64;y++)for(unsigned x=32;x<96;x++){
  unsigned value=source_pixels[(y-16)*width+x-16];
  for(unsigned k=0;k<3;k++){unsigned shift=k==0?11:k==1?5:0,mask=k==1?63:31;unsigned expected=(((k==0?31:0)*128)+((value>>shift)&mask)*127+127)/255;int delta=(int)expected-(int)((pixels[y*width+x]>>shift)&mask);if(delta>1||delta< -1)alpha_bad++;}
 }
 printf("shared_transparent_overlay pixels=2048 channels_beyond_one_RGB565_step=%u\n",alpha_bad);fflush(stdout);assert(!alpha_bad);
 if(direct){
  /* Compare preserved display pixels with a separate full render every time.
   * The fake presenter has padded rows and guards; no physical display writes. */
  w.width=width;w.height=height;w.stride=(width+8)*2;
  uint16_t *fb=malloc((height*(width+8)+64)*2);assert(fb);
  for(unsigned i=0;i<height*(width+8)+64;i++)fb[i]=0xa55a;
  w.pixels=fb+32;assert(!setenv("POCKET_SCENE_DAMAGE_ROOM","1",1));
  uint64_t reused=gs->device->preserved_frames;
  for(unsigned pass=0;pass<7;pass++){
   if(pass==2)assert(pocket_scene_room(s,room,.8f,20,0,.08f,.03f,340)>0);
   int offset=pass>=3?24:16;
   cells[1]^=0xffff;assert(!pocket_scene_cells(s,cells,cols,rows,0));
   assert(!pocket_scene_begin(s));
   if(pass==4){Scene_Rect clip={32,32,160,160};assert(!Scene_RenderSetClipRect(gs->device,&clip));}
   assert(!pocket_scene_image(s,room,offset,16));if(pass==4){struct scene_command *c=gs->canvas->commands+gs->canvas->count-1;c->clipped=1;c->clip=(Scene_Rect){32,32,160,160};}
   assert(!Scene_RenderSetClipRect(gs->device,NULL));
   if(pass==6){assert(!Scene_SetRenderDrawColor(gs->device,255,0,0,128));assert(!Scene_SetRenderDrawBlendMode(gs->device,Scene_BLENDMODE_BLEND));assert(!Scene_RenderFillRect(gs->device,&overlay));}
   assert(!Scene_PresentTarget(gs->device,gs->canvas));
   assert(gs->device->preserved_frames==reused+(pass>=1?1:0));
   assert(!pocket_scene_capture(s,pixels,width*height*2));
   /* Re-record and render all geometry into GL, bypassing presented capture. */
   assert(!pocket_scene_begin(s));
   if(pass==4){Scene_Rect clip={32,32,160,160};assert(!Scene_RenderSetClipRect(gs->device,&clip));}
   assert(!pocket_scene_image(s,room,offset,16));if(pass==4){struct scene_command *c=gs->canvas->commands+gs->canvas->count-1;c->clipped=1;c->clip=(Scene_Rect){32,32,160,160};}assert(!Scene_RenderSetClipRect(gs->device,NULL));
   if(pass==6){assert(!Scene_SetRenderDrawColor(gs->device,255,0,0,128));assert(!Scene_SetRenderDrawBlendMode(gs->device,Scene_BLENDMODE_BLEND));assert(!Scene_RenderFillRect(gs->device,&overlay));}
   assert(!Scene_RenderReadPixels(gs->device,NULL,Scene_PIXELFORMAT_RGB565,reference,width*2));
   assert(!memcmp(pixels,reference,width*height*2));
   for(unsigned y=0;y<height;y++){assert(!memcmp((char*)w.pixels+y*w.stride,reference+y*width,width*2));for(unsigned x=width;x<width+8;x++)assert(((uint16_t*)w.pixels)[y*(width+8)+x]==0xa55a);}
  }
  for(unsigned i=0;i<32;i++)assert(fb[i]==0xa55a&&fb[32+height*(width+8)+i]==0xa55a);
  printf("shared_damage_room cases=7 exact_pixels=1 preserved_frames=%llu guards=clean\n",(unsigned long long)(gs->device->preserved_frames-reused));fflush(stdout);
  free(fb);w.pixels=NULL;
 }
 free(source_pixels);free(reference);pocket_scene_texture_free(room);
#endif
 uint64_t stats[5];assert(!pocket_scene_stats(s,stats));assert(stats[3]>=1);for(unsigned i=0;i<32;i++)assert(allocation[i]==0xa55a&&allocation[32+width*height+i]==0xa55a);pocket_scene_close(s);free(allocation);OSMesaDestroyContext(gl);return 0;
}
