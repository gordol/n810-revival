"""Exercise the actual output planner with synthetic dense retained geometry."""
from pathlib import Path
import subprocess, tempfile, os
root=Path(__file__).resolve().parent
source=(root/'native/scene_backend_gl.h').read_text()
start=source.index('#define SCENE_TILE_TRIANGLES')
end=source.index('static int scene_gl_flush',start)
code=r'''
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <math.h>
#include <stdint.h>
typedef unsigned GLuint;
struct scene_gl_tile {GLuint color,fbo,depth;unsigned x,y,w,h,pw,ph;};
typedef struct {float x,y;} Point;
typedef struct {Point position;} Scene_Vertex;
typedef struct scene_texture_gl Scene_Texture;
struct scene_command {Scene_Texture *source;size_t first;int count,dx,dy;};
struct scene_texture_gl {unsigned n,format;int clear_pending,damage_valid,room_region,recorded_scene;size_t count;struct scene_command *commands;Scene_Vertex *stream;struct scene_gl_tile *tiles;};
typedef struct {int sink_dma,matrix_valid;} Scene_Renderer;
enum {Scene_PIXELFORMAT_RGB565=1,GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_TEXTURE_MAG_FILTER,GL_NEAREST,GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE,GL_RGB565,GL_RGBA,GL_UNSIGNED_BYTE,GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_FRAMEBUFFER_COMPLETE,GL_NO_ERROR};
#define glBindTexture(...) ((void)0)
#define glTexParameteri(...) ((void)0)
#define glTexImage2D(...) ((void)0)
#define glFramebufferTexture2D(...) ((void)0)
#define glDeleteFramebuffers(...) ((void)0)
#define glDeleteTextures(...) ((void)0)
#define glDeleteRenderbuffers(...) ((void)0)
#define glGenTextures(n,p) (*(p)=1)
#define glGenFramebuffers(n,p) (*(p)=2)
#define glCheckFramebufferStatus(...) GL_FRAMEBUFFER_COMPLETE
#define glGetError() GL_NO_ERROR
#define scene_gl_bind(...) ((void)0)
'''+source[start:end]+r'''
int main(void){
 Scene_Renderer r={.sink_dma=1};
 Scene_Vertex vertices[12000];
 for(unsigned i=0;i<4000;i++){
  float x=80+(i%80)*8,y=48+((i/80)%40)*8;
  vertices[3*i].position=(Point){x,y};vertices[3*i+1].position=(Point){x+5,y};vertices[3*i+2].position=(Point){x,y+5};
 }
 struct scene_command command={.count=12000};
 Scene_Texture t={.n=1,.format=1,.clear_pending=1,.count=1,.commands=&command,.stream=vertices};
 t.tiles=calloc(1,sizeof(*t.tiles));t.tiles[0]=(struct scene_gl_tile){.w=800,.h=480};
 assert(scene_bound_output(&r,&t)==0);assert(t.n>1);
 unsigned area=0;
 for(unsigned i=0;i<t.n;i++){
  struct scene_gl_tile *a=t.tiles+i;assert(scene_tile_triangles(&t,a,0,0,0)<=768);assert(a->pw<=400&&a->ph<=400);area+=a->w*a->h;
  for(unsigned j=i+1;j<t.n;j++){struct scene_gl_tile *b=t.tiles+j;assert(a->x+a->w<=b->x||b->x+b->w<=a->x||a->y+a->h<=b->y||b->y+b->h<=a->y);}
 }
 assert(area==800*480);assert(t.stream==vertices&&t.commands==&command&&command.count==12000);
 unsigned before=t.n;assert(!scene_bound_output(&r,&t)&&t.n==before);
 Scene_Texture nested=t;nested.recorded_scene=1;
 struct scene_command parent={.source=&nested,.dx=1000};
 Scene_Texture outer={.count=1,.commands=&parent};
 struct scene_gl_tile screen={.w=800,.h=480};assert(scene_tile_triangles(&outer,&screen,0,0,0)==0);
 parent.dx=0;assert(scene_tile_triangles(&outer,&screen,0,0,0)>768);
 printf("PASS: 4000 triangles split into %u disjoint GPU tiles; geometry retained; nested translations respected\n",t.n);free(t.tiles);
 /* 800 primitives split into two low-density 400x480 halves. Triangle-only
  * admission previously stopped there and failed on the actual GPU. */
 command.count=2400;t.n=1;t.tiles=calloc(1,sizeof(*t.tiles));t.tiles[0]=(struct scene_gl_tile){.w=800,.h=480};
 assert(!scene_bound_output(&r,&t));assert(t.n==4);area=0;
 for(unsigned i=0;i<t.n;i++){struct scene_gl_tile *q=t.tiles+i;assert(q->pw<=400&&q->ph<=400);assert(scene_tile_triangles(&t,q,0,0,0)<=768);area+=q->w*q->h;}
 assert(area==800*480);free(t.tiles);
 puts("PASS: sparse half-frame split preserves 800x480 output within admitted GPU dimensions");
 Scene_Texture room={.room_region=1};command.source=&room;command.count=6;
 t.n=1;t.tiles=calloc(1,sizeof(*t.tiles));t.tiles[0]=(struct scene_gl_tile){.w=800,.h=480,.depth=3};
 assert(!scene_bound_output(&r,&t));assert(t.n==4);area=0;
 for(unsigned i=0;i<t.n;i++){struct scene_gl_tile *q=t.tiles+i;assert(q->pw<=400&&q->ph<=400);assert(!q->depth);area+=q->w*q->h;}
 assert(area==800*480);unsigned room_tiles=t.n;assert(!scene_bound_output(&r,&t)&&t.n==room_tiles);free(t.tiles);
 puts("PASS: fused Room uses bounded regions even after a full-frame depth target");
}
'''
with tempfile.TemporaryDirectory(prefix='tile-budget-',dir=os.environ.get('TMPDIR')) as folder:
    c=Path(folder)/'check.c';c.write_text(code);binary=Path(folder)/'check'
    subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined',str(c),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
