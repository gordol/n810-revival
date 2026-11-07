/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
#define PY_SSIZE_T_CLEAN
#define Py_LIMITED_API 0x030b0000
#include <Python.h>
#include <OpenGL/gl.h>
#include <OpenGL/glext.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "cell_engine.c"
static const char *capsule_name="current_world.cells.v1";
typedef struct {uint32_t *order;size_t count;unsigned char *mask;} SceneInfo;
static void release_scene(PyObject *o){
 Surface *s=PyCapsule_GetPointer(o,capsule_name);SceneInfo *info=PyCapsule_GetContext(o);
 if(info){PyMem_Free(info->order);PyMem_Free(info->mask);PyMem_Free(info);}if(s)cw_free(s);else PyErr_Clear();
}
static PyObject *wrap(Surface *s){
 size_t n=(size_t)s->w*s->h;SceneInfo *info=PyMem_Calloc(1,sizeof(*info));
 if(!info){cw_free(s);return PyErr_NoMemory();}
 info->order=PyMem_Malloc(n*4);info->mask=PyMem_Malloc(n);info->count=n;
 if(!info->order||!info->mask){PyMem_Free(info->order);PyMem_Free(info->mask);PyMem_Free(info);cw_free(s);return PyErr_NoMemory();}
 for(size_t i=0;i<n;i++)info->order[i]=(uint32_t)i;memset(info->mask,1,n);
 PyObject *o=PyCapsule_New(s,capsule_name,release_scene);
 if(!o){PyMem_Free(info->order);PyMem_Free(info->mask);PyMem_Free(info);cw_free(s);return NULL;}
 PyCapsule_SetContext(o,info);return o;
}
static GLuint textures[6],fbo,program;static unsigned width,height;
static PyObject *base_ref;static uint64_t frames,flurry_frames,flux_frames,contributions,repairs,control_samples;
static const char *vertex="#version 120\nvoid main(){gl_Position=ftransform();gl_TexCoord[0]=gl_MultiTexCoord0;}";
static const char *fragment=
"#version 120\nuniform sampler2D sums,fore,back,density;uniform int effect_mode;uniform float phase_time,glow_scale;uniform vec2 viewport;\n"
"vec3 levels=vec3(31.,63.,31.);\n"
"vec3 quant(vec3 v){vec3 q=clamp(v,0.,255.)*levels/255.;vec3 lo=floor(q);vec3 f=q-lo;"
"q=lo+step(vec3(.5),f);return floor(q*255./levels+.5);}\n"
"float edge(vec3 v){vec3 q=clamp(v,0.,255.)*levels/255.;return float(any(lessThan(abs(fract(q)-.5),vec3(.012))));}\n"
"void main(){vec2 uv=gl_TexCoord[0].xy;vec4 s=texture2D(sums,uv);vec3 b=texture2D(back,uv).rgb;"
"vec3 f=texture2D(fore,uv).rgb;float e=0.;"
"if(effect_mode==0&&s.a>0.){vec3 rgb=min(s.rgb,215.);f=min(vec3(230.),b+rgb);b=min(vec3(220.),b+rgb*.45);e=max(edge(f),edge(b));f=quant(f);b=quant(b);}"
"if(effect_mode==1&&s.a>0.){vec3 d=texture2D(density,uv).rgb;float amount=min(2.2,s.r);"
"float phase=floor(uv.x*viewport.x)/viewport.x*2.4+floor(uv.y*viewport.y)/viewport.y*1.7+phase_time;"
"vec3 rgb=65.+85.*(.5+.5*sin(vec3(phase)+vec3(0.,2.1,4.2)));"
"if(d.r>0.){f=min(vec3(240.),b+rgb*amount*(d.g>0.?1.15:.65));b=b+rgb*amount*.08*glow_scale;}"
"else if(glow_scale>0.){f=b;b=b+rgb*amount*.20;}"
"if(d.r>0.||glow_scale>0.){e=max(edge(f),edge(b));f=quant(f);b=quant(b);}}"
"gl_FragData[0]=vec4(f,e);gl_FragData[1]=vec4(b,s.a);}";

static GLuint shader(GLenum kind,const char *source){
 GLuint s=glCreateShader(kind);glShaderSource(s,1,&source,NULL);glCompileShader(s);GLint ok=0;glGetShaderiv(s,GL_COMPILE_STATUS,&ok);
 if(!ok){char log[2048];glGetShaderInfoLog(s,sizeof(log),NULL,log);PyErr_SetString(PyExc_RuntimeError,log);glDeleteShader(s);return 0;}return s;
}
static int initialize(void){
 if(program)return 0;
 const char *renderer=(const char*)glGetString(GL_RENDERER);
 if(!renderer||strstr(renderer,"llvmpipe")||strstr(renderer,"softpipe")||strstr(renderer,"Software")){PyErr_SetString(PyExc_RuntimeError,"Hardware GPU context required; no CPU fallback");return -1;}
 GLuint v=shader(GL_VERTEX_SHADER,vertex),f=shader(GL_FRAGMENT_SHADER,fragment);
 if(!v||!f){if(v)glDeleteShader(v);if(f)glDeleteShader(f);return -1;}
 program=glCreateProgram();glAttachShader(program,v);glAttachShader(program,f);glLinkProgram(program);glDeleteShader(v);glDeleteShader(f);
 GLint ok=0;glGetProgramiv(program,GL_LINK_STATUS,&ok);if(!ok){PyErr_SetString(PyExc_RuntimeError,"GPU effect program link failed");return -1;}
 glGenTextures(6,textures);glGenFramebuffersEXT(1,&fbo);return 0;
}
static void texture(unsigned id,unsigned w,unsigned h,const float *data){
 glBindTexture(GL_TEXTURE_2D,textures[id]);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA32F_ARB,w,h,0,GL_RGBA,GL_FLOAT,data);
}
static unsigned packed(float r,float g,float b){return ((unsigned)r<<16)|((unsigned)g<<8)|(unsigned)b;}
static unsigned channel(double v,unsigned levels){if(v<0)v=0;if(v>255)v=255;return cw_even(cw_even(v*levels/255.)*255./levels);}
static uint64_t ink(double *f,double *b){unsigned fg=(channel(f[0],31)<<16)|(channel(f[1],63)<<8)|channel(f[2],31);unsigned bg=(channel(b[0],31)<<16)|(channel(b[1],63)<<8)|channel(b[2],31);return (UINT64_C(1)<<48)|((uint64_t)fg<<24)|bg;}
typedef struct {float x,y,r,g,b,a;double exact[3];int next;} Splat;
static int gpu_render(Surface *base,PyObject *base_obj,Splat *splat,unsigned count,float *pixels,int mode,double step,double glow,const float *field){
 size_t n=(size_t)base->w*base->h;
 GLint old_vertex_clamp,old_fragment_clamp;glGetIntegerv(GL_CLAMP_VERTEX_COLOR_ARB,&old_vertex_clamp);glGetIntegerv(GL_CLAMP_FRAGMENT_COLOR_ARB,&old_fragment_clamp);
 GLint old_fbo,old_program,old_active;glGetIntegerv(GL_FRAMEBUFFER_BINDING_EXT,&old_fbo);glGetIntegerv(GL_CURRENT_PROGRAM,&old_program);glGetIntegerv(GL_ACTIVE_TEXTURE,&old_active);
 glPushAttrib(GL_ALL_ATTRIB_BITS);glPushClientAttrib(GL_CLIENT_ALL_ATTRIB_BITS);
 glMatrixMode(GL_PROJECTION);glPushMatrix();glLoadIdentity();glOrtho(0,base->w,0,base->h,-1,1);glMatrixMode(GL_MODELVIEW);glPushMatrix();glLoadIdentity();
 int error=initialize();if(error)goto gpu_restore;
 glDisable(GL_DEPTH_TEST);glDisable(GL_LIGHTING);glDisable(GL_VERTEX_PROGRAM_ARB);glDisable(GL_TEXTURE_2D);glDisable(GL_SCISSOR_TEST);glDisable(GL_DITHER);glViewport(0,0,base->w,base->h);
 glUseProgram(0);glClampColorARB(GL_CLAMP_VERTEX_COLOR_ARB,GL_FALSE);glClampColorARB(GL_CLAMP_FRAGMENT_COLOR_ARB,GL_FALSE);glBindFramebufferEXT(GL_FRAMEBUFFER_EXT,fbo);glActiveTexture(GL_TEXTURE0);
 if(width!=base->w||height!=base->h||base_ref!=base_obj){
  float *fore=calloc(n*4,sizeof(float)),*back=calloc(n*4,sizeof(float));
  if(!fore||!back){free(fore);free(back);PyErr_NoMemory();error=-1;goto gpu_restore;}
  for(size_t i=0;i<n;i++)for(unsigned c=0;c<3;c++){fore[i*4+c]=(float)((base->ink[i]>>(40-c*8))&255);back[i*4+c]=(float)((base->ink[i]>>(16-c*8))&255);}
  texture(0,base->w,base->h,NULL);texture(1,base->w,base->h,fore);texture(2,base->w,base->h,back);texture(3,base->w,base->h,NULL);texture(4,base->w,base->h,NULL);texture(5,base->w,base->h,NULL);
  free(fore);free(back);Py_XDECREF(base_ref);base_ref=base_obj;Py_INCREF(base_ref);width=base->w;height=base->h;
 }
 glFramebufferTexture2DEXT(GL_FRAMEBUFFER_EXT,GL_COLOR_ATTACHMENT0_EXT,GL_TEXTURE_2D,textures[0],0);
 glFramebufferTexture2DEXT(GL_FRAMEBUFFER_EXT,GL_COLOR_ATTACHMENT1_EXT,GL_TEXTURE_2D,0,0);
 glDrawBuffer(GL_COLOR_ATTACHMENT0_EXT);glReadBuffer(GL_COLOR_ATTACHMENT0_EXT);if(glCheckFramebufferStatusEXT(GL_FRAMEBUFFER_EXT)!=GL_FRAMEBUFFER_COMPLETE_EXT){PyErr_SetString(PyExc_RuntimeError,"Float GPU accumulation target unavailable");error=-1;goto gpu_restore;}
 glClearColor(0,0,0,0);glClear(GL_COLOR_BUFFER_BIT);glEnable(GL_BLEND);glBlendFunc(GL_ONE,GL_ONE);glPointSize(1);
 glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_COLOR_ARRAY);glVertexPointer(2,GL_FLOAT,sizeof(Splat),&splat[0].x);glColorPointer(4,GL_FLOAT,sizeof(Splat),&splat[0].r);glDrawArrays(GL_POINTS,0,count);
 glDisable(GL_BLEND);glDisableClientState(GL_VERTEX_ARRAY);glDisableClientState(GL_COLOR_ARRAY);
 glFramebufferTexture2DEXT(GL_FRAMEBUFFER_EXT,GL_COLOR_ATTACHMENT0_EXT,GL_TEXTURE_2D,textures[3],0);glFramebufferTexture2DEXT(GL_FRAMEBUFFER_EXT,GL_COLOR_ATTACHMENT1_EXT,GL_TEXTURE_2D,textures[4],0);
 GLenum buffers[2]={GL_COLOR_ATTACHMENT0_EXT,GL_COLOR_ATTACHMENT1_EXT};glDrawBuffers(2,buffers);glUseProgram(program);
 for(unsigned i=0;i<4;i++){glActiveTexture(GL_TEXTURE0+i);glBindTexture(GL_TEXTURE_2D,textures[i==3?5:i]);}
 if(mode){glActiveTexture(GL_TEXTURE3);texture(5,base->w,base->h,field);}
 glUniform1i(glGetUniformLocation(program,"effect_mode"),mode);glUniform1f(glGetUniformLocation(program,"phase_time"),(float)(step/90*.12));glUniform1f(glGetUniformLocation(program,"glow_scale"),(float)glow);glUniform2f(glGetUniformLocation(program,"viewport"),base->w,base->h);glUniform1i(glGetUniformLocation(program,"density"),3);
 glUniform1i(glGetUniformLocation(program,"sums"),0);glUniform1i(glGetUniformLocation(program,"fore"),1);glUniform1i(glGetUniformLocation(program,"back"),2);
 glBegin(GL_QUADS);glTexCoord2f(0,0);glVertex2f(0,0);glTexCoord2f(1,0);glVertex2f(base->w,0);glTexCoord2f(1,1);glVertex2f(base->w,base->h);glTexCoord2f(0,1);glVertex2f(0,base->h);glEnd();
 glReadBuffer(GL_COLOR_ATTACHMENT0_EXT);glReadPixels(0,0,base->w,base->h,GL_RGBA,GL_FLOAT,pixels);glReadBuffer(GL_COLOR_ATTACHMENT1_EXT);glReadPixels(0,0,base->w,base->h,GL_RGBA,GL_FLOAT,pixels+n*4);
 if(glGetError()!=GL_NO_ERROR){PyErr_SetString(PyExc_RuntimeError,"GPU effect execution failed; no CPU fallback");error=-1;goto gpu_restore;}
gpu_restore:
 glClampColorARB(GL_CLAMP_VERTEX_COLOR_ARB,old_vertex_clamp);glClampColorARB(GL_CLAMP_FRAGMENT_COLOR_ARB,old_fragment_clamp);
 glUseProgram((GLuint)old_program);glBindFramebufferEXT(GL_FRAMEBUFFER_EXT,(GLuint)old_fbo);glActiveTexture((GLenum)old_active);
 glMatrixMode(GL_MODELVIEW);glPopMatrix();glMatrixMode(GL_PROJECTION);glPopMatrix();glPopClientAttrib();glPopAttrib();
 return error;
}
static PyObject *flurry(PyObject *self,PyObject *args){
 (void)self;PyObject *base_obj,*plan_obj;double step,sway,speed;int ascii;
 if(!PyArg_ParseTuple(args,"OOdddp",&base_obj,&plan_obj,&step,&sway,&speed,&ascii))return NULL;
 Surface *base=PyCapsule_GetPointer(base_obj,capsule_name);if(!base)return NULL;
 if(!isfinite(step)||!isfinite(sway)||!isfinite(speed)||fabs(step)>1e6||base->w>512||base->h>256){PyErr_SetString(PyExc_ValueError,"Unsupported effect bounds");return NULL;}
 Py_buffer plan;if(PyObject_GetBuffer(plan_obj,&plan,PyBUF_CONTIG_RO))return NULL;
 if(plan.len%32||plan.len<8*32||plan.len>192*32){PyBuffer_Release(&plan);PyErr_SetString(PyExc_ValueError,"Invalid Flurry plan");return NULL;}
 size_t n=(size_t)base->w*base->h;unsigned max=(unsigned)(plan.len/32)*120;Splat *splat=calloc(max,sizeof(*splat));int *first=malloc(n*sizeof(int)),*last=malloc(n*sizeof(int));
 float *pixels=calloc(n*8,sizeof(float));Surface *result=cw_surface(base->w,base->h);PyObject *answer=NULL;
 if(!splat||!first||!last||!pixels||!result){PyErr_NoMemory();goto done;}
 for(size_t i=0;i<n;i++)first[i]=last[i]=-1;
 unsigned count=0,used=0;const double *p=plan.buf;const double colors[4][3]={{45,170,125},{113,105,200},{195,117,68},{80,175,193}};double age=step/24*speed;
 for(unsigned strand=0;strand<(unsigned)plan.len/32;strand++){
  double phase=p[strand*4],radius=p[strand*4+1],rate=p[strand*4+2];unsigned group=(unsigned)p[strand*4+3];
  if(group>3||!isfinite(phase)||!isfinite(radius)||!isfinite(rate)){PyErr_SetString(PyExc_ValueError,"Invalid Flurry control");goto done;}
  double previous_x=0,previous_y=0;
  for(unsigned trail=0;trail<20;trail++){
   double t=age-trail*.035,angle=phase+t*rate*(group%2?1:-1),twist=sin(t*.21+phase*2)*.28*(sway/.6);
   double cx=.5+.11*sin(t*.07+group*1.7),cy=.5+.10*cos(t*.08+group),v=sin(phase+t*.11),depth=.55+.45*v*v;
   double x=(cx+cos(angle+twist)*radius*.47*depth)*base->w,y=(cy+sin(angle*1.01)*radius*.46*depth)*base->h;
   double strength=(1-trail/21.)*(.35+.65*depth);
   for(unsigned point=0;point<(trail?2u:1u);point++){
    double px=point?(x+previous_x)/2:x,py=point?(y+previous_y)/2:y;
    for(unsigned offset=0;offset<3;offset++){
     int xx=(int)px+(offset==1?-1:offset==2?1:0),yy=(int)py;
     if(xx<0||yy<0||xx>=(int)base->w||yy>=(int)base->h)continue;
     unsigned index=(unsigned)yy*base->w+(unsigned)xx;
     if(first[index]<0){if(used>=16384)continue;used++;}
     Splat *s=splat+count;s->x=xx+.5f;s->y=yy+.5f;s->a=1;s->next=-1;
     for(unsigned c=0;c<3;c++)s->exact[c]=colors[group][c]*strength*(offset?.22:1)*.32;
     s->r=(float)s->exact[0];s->g=(float)s->exact[1];s->b=(float)s->exact[2];
     if(last[index]>=0)splat[last[index]].next=(int)count;else first[index]=(int)count;
     last[index]=(int)count++;
    }
   }
   previous_x=x;previous_y=y;
  }
 }
 int error=gpu_render(base,base_obj,splat,count,pixels,0,step,0,NULL);if(error)goto done;
 for(size_t i=0;i<n;i++){
  uint64_t color=(UINT64_C(1)<<48)|((uint64_t)packed(pixels[i*4],pixels[i*4+1],pixels[i*4+2])<<24)|packed(pixels[(n+i)*4],pixels[(n+i)*4+1],pixels[(n+i)*4+2]);
  if(pixels[i*4+3]>.5f&&first[i]>=0){
   double sum[3]={0,0,0},fg[3],bg[3];for(int at=first[i];at>=0;at=splat[at].next)for(unsigned c=0;c<3;c++){sum[c]+=splat[at].exact[c];if(sum[c]>215)sum[c]=215;}
   for(unsigned c=0;c<3;c++){double under=(base->ink[i]>>(16-c*8))&255;fg[c]=fmin(230,under+sum[c]);bg[c]=fmin(220,under+sum[c]*.45);}
   color=ink(fg,bg);repairs++;
  }
  cw_set(result,(uint32_t)i,first[i]>=0?(ascii?':':0x2584):base->glyph[i],color,1);
 }
 frames++;flurry_frames++;control_samples+=(unsigned)(plan.len/32)*20;contributions+=count;

 answer=wrap(result);result=NULL;
done:
 PyBuffer_Release(&plan);free(splat);free(first);free(last);free(pixels);cw_free(result);return answer;
}
static int even_round(double x){double lo=floor(x),v=x-lo;return (int)(lo+(v>.5||(v==.5&&fmod(lo,2)!=0)));}
static PyObject *flux(PyObject *self,PyObject *args){
 (void)self;PyObject *base_obj;double step,scale,glow;int ascii,arms;
 if(!PyArg_ParseTuple(args,"Odddip",&base_obj,&step,&scale,&glow,&arms,&ascii))return NULL;
 Surface *base=PyCapsule_GetPointer(base_obj,capsule_name);if(!base)return NULL;
 if(!isfinite(step)||!isfinite(scale)||!isfinite(glow)||fabs(step)>1e6||glow<0||glow>1||arms<0||arms>4||base->w>512||base->h>256){PyErr_SetString(PyExc_ValueError,"Unsupported Flux bounds");return NULL;}
 unsigned w=base->w,h=base->h;size_t n=(size_t)w*h;
 double *density=calloc(n,sizeof(double));uint32_t *heads=calloc(n,4),*order=malloc(n*4);char *trails=calloc(n,1);
 float *field=calloc(n*4,sizeof(float)),*pixels=calloc(n*8,sizeof(float));int *first=malloc(n*sizeof(int)),*last=malloc(n*sizeof(int));
 Splat *splat=NULL;Surface *result=cw_surface(w,h);PyObject *answer=NULL;
 if(!density||!heads||!order||!trails||!field||!pixels||!first||!last||!result){PyErr_NoMemory();goto done_flux;}
 for(size_t i=0;i<n;i++)first[i]=last[i]=-1;
 double t=step/90,a=-1.4+.12*sin(t),b=1.6,c=1+.15*cos(t*.7),d=.7,x=.1,y=.1;
 unsigned budget=(unsigned)(n/8);if(budget<64)budget=64;if(budget>768)budget=768;budget=cw_even(budget*(scale<.5?.5:scale>4?4:scale));unsigned count=0;
 for(unsigned i=0;i<budget+32;i++){
  double nx=sin(a*y)+c*cos(a*x),ny=sin(b*x)+d*cos(b*y);x=nx;y=ny;if(i<32)continue;
  int xx=(int)((x+2.2)/4.4*w),yy=(int)((y+2)/4*h);if(xx<0)xx=0;if(xx>=(int)w)xx=w-1;if(yy<0)yy=0;if(yy>=(int)h)yy=h-1;
  unsigned at=(unsigned)yy*w+(unsigned)xx;if(!density[at])order[count++]=at;density[at]+=1;
 }
 unsigned primary=count;for(unsigned k=0;k<primary;k++)heads[order[k]]=(uint32_t)density[order[k]];
 for(unsigned k=0;k<primary;k++){
  unsigned at=order[k],xx=at%w,yy=at/w;double angle=sin((double)xx/w*5+t*.3)+(double)yy/h*3,dx=cos(angle),dy=sin(angle)*.5;
  char glyph=fabs(dy)<.25?'-':dx*dy<0?'/':'\\';
  for(int distance=1;distance<=arms;distance++){
   int tx=even_round(xx-dx*distance),ty=even_round(yy-dy*distance);if(tx<0||ty<0||tx>=(int)w||ty>=(int)h)continue;
   unsigned index=(unsigned)ty*w+(unsigned)tx;if(heads[index])continue;double weight=(1-(double)distance/(arms+1))*.65;
   if(!density[index])order[count++]=index;if(density[index]<weight)density[index]=weight;trails[index]=glyph;
  }
 }
 splat=calloc((size_t)count*5,sizeof(*splat));if(!splat){PyErr_NoMemory();goto done_flux;}
 unsigned emitted=0;
 for(unsigned k=0;k<count;k++){
  unsigned at=order[k];int xx=at%w,yy=at/w;double strength=fmin(1.7,.45+log1p(density[at])*.35);
  const int dx[5]={0,-1,1,0,0},dy[5]={0,0,0,-1,1};const double weights[5]={1,.18,.18,.12,.12};
  for(unsigned j=0;j<5;j++){
   int tx=xx+dx[j],ty=yy+dy[j];if(tx<0||ty<0||tx>=(int)w||ty>=(int)h)continue;
   unsigned index=(unsigned)ty*w+(unsigned)tx;Splat *s=splat+emitted;
   s->x=tx+.5f;s->y=ty+.5f;s->exact[0]=strength*weights[j]*(j?glow:1);s->r=(float)s->exact[0];s->a=1;s->next=-1;
   if(last[index]>=0)splat[last[index]].next=(int)emitted;else first[index]=(int)emitted;
   last[index]=(int)emitted++;
  }
 }
 for(size_t i=0;i<n;i++){field[i*4]=(float)density[i];field[i*4+1]=(float)heads[i];}
 if(gpu_render(base,base_obj,splat,emitted,pixels,1,step,glow,field))goto done_flux;
 for(size_t i=0;i<n;i++){
  uint64_t color=(UINT64_C(1)<<48)|((uint64_t)packed(pixels[i*4],pixels[i*4+1],pixels[i*4+2])<<24)|packed(pixels[(n+i)*4],pixels[(n+i)*4+1],pixels[(n+i)*4+2]);
  unsigned glyph=base->glyph[i];int active=first[i]>=0&&(density[i]>0||glow>0);
  if(active)glyph=density[i]>0?(trails[i]?(unsigned)trails[i]:heads[i]>=3?'+':ascii?'.':0xb7):' ';
  if(active&&pixels[i*4+3]>.5f){
   double amount=0,fg[3],bg[3];for(int at=first[i];at>=0;at=splat[at].next)amount=fmin(2.2,amount+splat[at].exact[0]);
   double phase=(double)(i%w)/w*2.4+(double)(i/w)/h*1.7+t*.12;
   for(unsigned channel_id=0;channel_id<3;channel_id++){
    double under=(base->ink[i]>>(16-channel_id*8))&255,rgb=65+85*(.5+.5*sin(phase+channel_id*2.1));
    fg[channel_id]=density[i]>0?fmin(240,under+rgb*amount*(heads[i]?1.15:.65)):under;
    bg[channel_id]=under+rgb*amount*(density[i]>0?.08*glow:.20);
   }
   color=ink(fg,bg);repairs++;
  }
  cw_set(result,(uint32_t)i,glyph,color,1);
 }
 frames++;flux_frames++;control_samples+=budget+32;contributions+=emitted;answer=wrap(result);result=NULL;
done_flux:
 free(density);free(heads);free(order);free(trails);free(field);free(pixels);free(first);free(last);free(splat);cw_free(result);return answer;
}

#include "gpu_composition.c"
static PyObject *stats(PyObject *self,PyObject *unused){(void)self;(void)unused;return Py_BuildValue("{sK,sK,sK,sK,sK,sK,sK,sK,sK,ss}","gpu_frames",frames,"flurry_gpu_frames",flurry_frames,"flux_gpu_frames",flux_frames,"gpu_splats",contributions,"precision_cells",repairs,"cpu_control_samples",control_samples,"composition_frames",composition_frames,"composed_cells",composed_cells,"composition_repairs",composition_repairs,"backend","OpenGL GPU accumulation, shading and cell composition");}
static PyMethodDef methods[]={{"blend_scene",gpu_blend,METH_VARARGS,"GPU window material and shadow composition."},{"compose",gpu_compose,METH_VARARGS,"GPU opaque layer composition."},{"flux",flux,METH_VARARGS,"GPU glow accumulation and shading with exact edge repair."},{"flurry",flurry,METH_VARARGS,"GPU ribbon accumulation and shading with exact edge repair."},{"stats",stats,METH_NOARGS,"Actual submitted GPU work."},{NULL,NULL,0,NULL}};
static struct PyModuleDef module={PyModuleDef_HEAD_INIT,"_gpueffects",NULL,-1,methods,NULL,NULL,NULL,NULL};
PyMODINIT_FUNC PyInit__gpueffects(void){return PyModule_Create(&module);}
