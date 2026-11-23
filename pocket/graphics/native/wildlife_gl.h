/* SDL OpenGL renderer interop. The canvas is already bound as a framebuffer.
 * SDL stores target textures bottom row first (canvas Y increases in GL Y). */
#define GL_GLEXT_PROTOTYPES
#include <SDL_opengl.h>
#include <stddef.h>

struct wildlife_gl {
 GLuint program, buffer, depth;
 unsigned width,height,key,count;
};
struct wildlife_vertex {float a[4],b[4];unsigned char color[4];};

static GLuint wildlife_shader(GLenum kind,const char *src){
 GLuint shader=glCreateShader(kind);
 glShaderSource(shader,1,&src,NULL);glCompileShader(shader);
 GLint ok;glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
 if(!ok){
  char log[512];glGetShaderInfoLog(shader,sizeof(log),NULL,log);
  SDL_SetError("Wildlife shader: %s",log);glDeleteShader(shader);return 0;
 }
 return shader;
}

static GLuint wildlife_program(void){
 const char *vertex="#version 120\n"
  "uniform float phase; varying vec3 local; varying vec3 coat;"
  "void main(){vec4 p=mix(gl_Vertex,gl_MultiTexCoord0,phase);local=gl_Vertex.xyz;"
  "coat=gl_Color.rgb*p.w;gl_Position=gl_ModelViewProjectionMatrix*vec4(p.xyz,1.);}";
 const char *fragment="#version 120\n"
  "varying vec3 local; varying vec3 coat; uniform float grainStrength;"
  "float hash(vec3 p){p=fract(p*.1031);p+=dot(p,p.yzx+33.33);return fract((p.x+p.y)*p.z);}"
  "float grain(vec3 p){vec3 i=floor(p),u=fract(p);u=u*u*(3.-2.*u);"
  "return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),u.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),u.x),u.y),"
  "mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),u.x),mix(hash(i+vec3(0,1,1)),hash(i+1.),u.x),u.y),u.z);}"
  "void main(){vec3 p=local;p.y+=.11*p.x+.012*sin(p.x*15.);"
  "float fur=grain(p*vec3(90.,530.,490.));float m=grain(p*vec3(15.,35.,32.));"
  "gl_FragColor=vec4(coat*(1.+grainStrength*((fur-.5)+.62*(m-.5))),1.);}";
 GLuint vs=wildlife_shader(GL_VERTEX_SHADER,vertex);if(!vs)return 0;
 GLuint fs=wildlife_shader(GL_FRAGMENT_SHADER,fragment);if(!fs){glDeleteShader(vs);return 0;}
 GLuint program=glCreateProgram();glAttachShader(program,vs);glAttachShader(program,fs);
 glLinkProgram(program);glDeleteShader(vs);glDeleteShader(fs);
 GLint linked;glGetProgramiv(program,GL_LINK_STATUS,&linked);
 if(!linked){glDeleteProgram(program);SDL_SetError("Wildlife shader link failed");return 0;}
 return program;
}

static void wildlife_gl_close(struct wildlife_gl *g){
 glDeleteBuffers(1,&g->buffer);glDeleteRenderbuffers(1,&g->depth);glDeleteProgram(g->program);
}

static int wildlife_upload(struct wildlife_gl *g,const float *a,const float *b,unsigned nv,
                           const unsigned *faces,unsigned nf,unsigned key){
 struct wildlife_vertex *v=malloc(3*nf*sizeof(*v));if(!v)return SDL_OutOfMemory();
 for(unsigned i=0;i<nf;i++){
  const unsigned *f=faces+4*i;
  for(unsigned k=0;k<3;k++){
   if(f[k]>=nv){free(v);return SDL_SetError("Invalid wildlife triangle");}
   struct wildlife_vertex *p=v+3*i+k;
   memcpy(p->a,a+4*f[k],sizeof(p->a));memcpy(p->b,b+4*f[k],sizeof(p->b));
   p->color[0]=f[3]>>16;p->color[1]=f[3]>>8;p->color[2]=f[3];p->color[3]=255;
  }
 }
 glBufferData(GL_ARRAY_BUFFER,3*nf*sizeof(*v),v,GL_STATIC_DRAW);free(v);
 g->count=3*nf;g->key=key;return 0;
}

static int wildlife_gl_draw(struct wildlife_gl *g,int x,int y,int w,int h,unsigned cw,unsigned ch,
                            const float *a,const float *b,unsigned nv,const unsigned *faces,unsigned nf,
                            float blend,float yaw,float tilt,float scale,float bob,int appearance,unsigned key){
 const int flight=appearance==1;
 if(!g->program){
  g->program=wildlife_program();if(!g->program)return -1;
  glGenBuffers(1,&g->buffer);glGenRenderbuffers(1,&g->depth);
 }
 GLint previous_program,previous_buffer,previous_depth;
 glGetIntegerv(GL_CURRENT_PROGRAM,&previous_program);glGetIntegerv(GL_ARRAY_BUFFER_BINDING,&previous_buffer);
 glGetIntegerv(GL_RENDERBUFFER_BINDING,&previous_depth);
 glPushAttrib(GL_ALL_ATTRIB_BITS);glPushClientAttrib(GL_CLIENT_VERTEX_ARRAY_BIT);
 glBindBuffer(GL_ARRAY_BUFFER,g->buffer);
 int result=0;
 if((!g->count||g->key!=key)&&wildlife_upload(g,a,b,nv,faces,nf,key)){result=-1;goto done;}
 glBindRenderbuffer(GL_RENDERBUFFER,g->depth);
 if(cw!=g->width||ch!=g->height){
  glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT24,cw,ch);g->width=cw;g->height=ch;
 }
 glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,g->depth);
 if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE){
  result=SDL_SetError("Incomplete wildlife depth framebuffer");goto detach;
 }
 glViewport(x,y,w,h);glEnable(GL_SCISSOR_TEST);glScissor(x,y,w,h);
 glDisable(GL_BLEND);glDisable(GL_CULL_FACE);glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LEQUAL);
 glDepthMask(GL_TRUE);glClearDepth(1.);
 if(flight)glClearColor(.56f,.69f,.76f,1.f);else glClearColor(.51f,.55f,.47f,1.f);
 glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
 glMatrixMode(GL_PROJECTION);glPushMatrix();glLoadIdentity();glOrtho(-w/(2*scale),w/(2*scale),h/(2*scale),-h/(2*scale),-4,4);
 glMatrixMode(GL_MODELVIEW);glPushMatrix();glLoadIdentity();
 glRotatef(tilt*57.29578f,1,0,0);glRotatef(180.f+yaw*57.29578f,0,1,0);glScalef(-1,1,1);
 glTranslatef(0,bob-(flight?0.f:.30f),0);
 glUseProgram(g->program);glUniform1f(glGetUniformLocation(g->program,"phase"),blend);
 glUniform1f(glGetUniformLocation(g->program,"grainStrength"),appearance==2?.065f:(flight?.14f:.29f));
 glClientActiveTexture(GL_TEXTURE0);
 glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_TEXTURE_COORD_ARRAY);glEnableClientState(GL_COLOR_ARRAY);
 glVertexPointer(4,GL_FLOAT,sizeof(struct wildlife_vertex),(void*)offsetof(struct wildlife_vertex,a));
 glTexCoordPointer(4,GL_FLOAT,sizeof(struct wildlife_vertex),(void*)offsetof(struct wildlife_vertex,b));
 glColorPointer(4,GL_UNSIGNED_BYTE,sizeof(struct wildlife_vertex),(void*)offsetof(struct wildlife_vertex,color));
 glDrawArrays(GL_TRIANGLES,0,(GLsizei)g->count);
 glPopMatrix();glMatrixMode(GL_PROJECTION);glPopMatrix();
detach:
 glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,0);
done:
 glUseProgram(previous_program);glBindRenderbuffer(GL_RENDERBUFFER,previous_depth);
 glPopClientAttrib();glBindBuffer(GL_ARRAY_BUFFER,previous_buffer);glPopAttrib();
 return result;
}
