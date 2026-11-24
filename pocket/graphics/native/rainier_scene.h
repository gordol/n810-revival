/* Static world-space terrain and vegetation. Use the SDL OpenGL canvas
 * directly, preserving the renderer state used by subsequent UI drawing. */
static GLuint rainier_program(void){
 const char *vs="#version 120\n"
  "varying vec3 pos;varying vec4 tint;varying float distanceToEye;"
  "uniform float poseBlend;"
  "void main(){pos=mix(gl_Vertex.xyz,gl_MultiTexCoord0.xyz,poseBlend);tint=gl_Color;"
  "vec4 eye=gl_ModelViewMatrix*vec4(pos,1.);"
  "distanceToEye=length(eye.xyz);gl_Position=gl_ProjectionMatrix*eye;}";
 const char *fs="#version 120\n"
  "varying vec3 pos;varying vec4 tint;varying float distanceToEye;"
  "uniform float waterTime;uniform vec3 picked;uniform int highDetail;uniform int animal;uniform sampler2D forestShade;"
  "float hash(vec2 p){vec3 q=fract(vec3(p.xyx)*.1031);q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}"
  "float noise(vec2 p){vec2 i=floor(p),u=fract(p);u=u*u*(3.-2.*u);"
  "return mix(mix(hash(i),hash(i+vec2(1,0)),u.x),mix(hash(i+vec2(0,1)),hash(i+1.),u.x),u.y);}"
  "void main(){if((abs(tint.a-.08)<.01 && picked.x>.5)||(abs(tint.a-.13)<.01 && picked.y>.5)||(abs(tint.a-.18)<.01 && picked.z>.5))discard;vec3 col=tint.rgb;if(tint.a>.9){vec2 p=pos.xz;"
  "float broad=noise(p*.015);float detail=(noise(p*.64)-.5)*(1.-smoothstep(80.,600.,distanceToEye));"
  "col*=.80+.40*broad+.30*detail;col+=vec3(.032,.024,-.013)*broad;"
  "if(highDetail!=0){float grit=noise(p*11.)-.5;float moss=noise(p*.18);"
  "col+=vec3(.075,.055,.026)*moss;col+=grit*vec3(.041,.037,.024)*(1.-smoothstep(6.,38.,distanceToEye));"
  "vec2 uv=p/512.+.5;float shade=texture2D(forestShade,uv).r*(1.-smoothstep(.45,.5,max(abs(uv.x-.5),abs(uv.y-.5))));"
  "col*=mix(vec3(1.1,1.09,1.02),vec3(.52,.64,.74),shade);}}"
  "if(highDetail!=0 && tint.a>.46 && tint.a<.50){float bark=noise(vec2((pos.x+pos.z)*21.,pos.y*2.6));col*=.68+.6*bark;}"
  "if(highDetail!=0 && tint.a>.06 && tint.a<.20){vec3 n=normalize(cross(dFdx(pos),dFdy(pos)));"
  "float wax=pow(abs(dot(n,normalize(vec3(-.42,.79,-.44)))),14.);col+=vec3(.28,.34,.43)*wax;}"
  "if(tint.a>.65 && tint.a<.85){float seams=noise(vec2(pos.x*.006,pos.z*.036+sin(pos.x*.007)));"
  "col*=1.-.25*smoothstep(.60,.78,seams);}"
  "if(tint.a>.25 && tint.a<.45){float ripples=noise(vec2(pos.x*3.,pos.z*2.+pos.y+waterTime*2.5));"
  "col=mix(col,vec3(.85,.94,.93),smoothstep(.58,.86,ripples)*.75);"
  "if(highDetail!=0){float glint=sin(pos.x*14.+pos.z*9.+waterTime*3.+4.*ripples);"
  "col+=vec3(.47,.49,.43)*smoothstep(.84,1.,glint)*smoothstep(.57,.85,ripples);}}"
  "if(highDetail!=0 && animal!=0 && distanceToEye<16.){float strands=noise(vec2((pos.x+.3*pos.z)*55.,(pos.y+.15*pos.x)*245.));"
  "col*=1.+.20*(strands-.5)*(1.-smoothstep(3.,16.,distanceToEye));}"
  "float haze=1.-exp(-distanceToEye*.00042);gl_FragColor=vec4(mix(col,vec3(.56,.70,.80),haze),1.);}";
 GLuint vert=wildlife_shader(GL_VERTEX_SHADER,vs);if(!vert)return 0;
 GLuint frag=wildlife_shader(GL_FRAGMENT_SHADER,fs);if(!frag){glDeleteShader(vert);return 0;}
 GLuint program=glCreateProgram();glAttachShader(program,vert);glAttachShader(program,frag);
 glLinkProgram(program);glDeleteShader(frag);glDeleteShader(vert);
 GLint ok;glGetProgramiv(program,GL_LINK_STATUS,&ok);
 if(!ok){SDL_SetError("Rainier terrain shader link failed");glDeleteProgram(program);return 0;}
 return program;
}

/* Sample a blurred copy of the scene before drawing the sharp trail controls. */
static GLuint river_bloom_program(void){
 const char *vs="#version 120\n varying vec2 uv;void main(){uv=gl_Vertex.xy*.5+.5;gl_Position=gl_Vertex;}";
 const char *fs="#version 120\n varying vec2 uv;uniform sampler2D scene;uniform vec2 stepUV;"
  "vec3 bright(vec2 p){vec3 c=texture2D(scene,p,2.).rgb;return c*smoothstep(.59,.92,max(c.r,max(c.g,c.b)));}"
  "void main(){vec3 b=bright(uv)*2.+bright(uv+stepUV)+bright(uv-stepUV)"
  "+bright(uv+vec2(stepUV.x,-stepUV.y))+bright(uv+vec2(-stepUV.x,stepUV.y));gl_FragColor=vec4(b*.032,0.);}";
 GLuint v=wildlife_shader(GL_VERTEX_SHADER,vs);if(!v)return 0;
 GLuint f=wildlife_shader(GL_FRAGMENT_SHADER,fs);if(!f){glDeleteShader(v);return 0;}
 GLuint program=glCreateProgram();glAttachShader(program,v);glAttachShader(program,f);glLinkProgram(program);
 glDeleteShader(v);glDeleteShader(f);GLint ok;glGetProgramiv(program,GL_LINK_STATUS,&ok);
 if(!ok){glDeleteProgram(program);return 0;}return program;
}

static void river_bloom(struct gpu_scene *s,int x,int y,int w,int h){
 if(!s->rainier_bloom && !s->rainier_bloom_failed){
  s->rainier_bloom=river_bloom_program();s->rainier_bloom_failed=!s->rainier_bloom;
 }
 if(!s->rainier_bloom||s->rainier_bloom_failed)return;
 if(!s->rainier_color)glGenTextures(1,&s->rainier_color);
 glBindTexture(GL_TEXTURE_2D,s->rainier_color);
 if(s->bloom_w!=w||s->bloom_h!=h){
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
  glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
  GLint allocated=0;glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_WIDTH,&allocated);
  if(allocated!=w){s->rainier_bloom_failed=1;return;}
  s->bloom_w=w;s->bloom_h=h;
 }
 glCopyTexSubImage2D(GL_TEXTURE_2D,0,0,0,x,y,w,h);glGenerateMipmap(GL_TEXTURE_2D);
 glUseProgram(s->rainier_bloom);glUniform2f(glGetUniformLocation(s->rainier_bloom,"stepUV"),4.f/w,4.f/h);
 glDisable(GL_DEPTH_TEST);glEnable(GL_BLEND);glBlendFunc(GL_ONE,GL_ONE);
 glBegin(GL_TRIANGLE_STRIP);glVertex2f(-1,-1);glVertex2f(1,-1);glVertex2f(-1,1);glVertex2f(1,1);glEnd();
 glDisable(GL_BLEND);
}

/* Consecutive triangles in the plant meshes are spatially coherent. Keep a
 * conservative bounding sphere per batch and combine adjacent visible draws. */
enum { RIVER_BATCH=384 };
static void river_bounds_build(struct gpu_scene *s,const float *vertices,unsigned count){
 free(s->river_blocks);s->river_blocks=calloc((count+RIVER_BATCH-1)/RIVER_BATCH,sizeof(*s->river_blocks));
 if(!s->river_blocks)return;
 for(unsigned first=0;first<count;first+=RIVER_BATCH){
  unsigned end=first+RIVER_BATCH<count?first+RIVER_BATCH:count;
  float lo[3],hi[3];memcpy(lo,vertices+7*first,sizeof(lo));memcpy(hi,lo,sizeof(hi));
  for(unsigned i=first+1;i<end;i++)for(int k=0;k<3;k++){
   float v=vertices[7*i+k];lo[k]=fminf(lo[k],v);hi[k]=fmaxf(hi[k],v);
  }
  float dx=hi[0]-lo[0],dy=hi[1]-lo[1],dz=hi[2]-lo[2];
  s->river_blocks[first/RIVER_BATCH]=(struct river_bounds){lo[0]+dx*.5f,lo[1]+dy*.5f,lo[2]+dz*.5f,.5f*sqrtf(dx*dx+dy*dy+dz*dz)+.01f};
 }
}

static void river_draw_land(struct gpu_scene *s,unsigned count,float x,float y,float z,float yaw,float pitch,float aspect){
 if(!s->river_blocks){glDrawArrays(GL_TRIANGLES,0,(GLsizei)count);return;}
 float sy=sinf(yaw),cy=cosf(yaw),sp=sinf(pitch),cp=cosf(pitch);
 float ty=.5543f,tx=ty*aspect,kx=sqrtf(1+tx*tx),ky=sqrtf(1+ty*ty);
 unsigned start=0;
 for(unsigned first=0;first<count;first+=RIVER_BATCH){
  struct river_bounds b=s->river_blocks[first/RIVER_BATCH];
  float dx=b.x-x,dy=b.y-y,dz=b.z-z;
  float forward=sy*dx+cy*dz,depth=cp*forward-sp*dy;
  if(depth+b.r<.2f || fabsf(cy*dx-sy*dz)>depth*tx+b.r*kx ||
     fabsf(sp*forward+cp*dy)>depth*ty+b.r*ky){
   if(first>start)glDrawArrays(GL_TRIANGLES,(GLint)start,(GLsizei)(first-start));
   start=first+RIVER_BATCH;
  }
 }
 if(count>start)glDrawArrays(GL_TRIANGLES,(GLint)start,(GLsizei)(count-start));
}

struct rainier_animal {
 unsigned first,second,index,count,stride;
 float blend,x,y,z,heading,shadow,slope_x,slope_z;
};

int pocket_scene_rainier(void *ptr,int x,int y,int w,int h,const float *vertices,unsigned count,
                         unsigned terrain_count,const unsigned *indices,unsigned ni,
                         const struct rainier_animal *animals,unsigned na,
                         float east,float eye,float north,float yaw,float pitch,float age,int picked,float direction,int fed,int high,const unsigned char *shadows){
 struct gpu_scene *s=ptr;
 if(!s||w<1||h<1||count<3||count>2000000||(!vertices&&!s->rainier_buffer))
  return SDL_SetError("Invalid Rainier scene");
 if(terrain_count>count||ni>2000000||na>64||(!animals&&na)||
    (!!vertices!=!!indices)||(!indices&&!s->rainier_indices))return SDL_SetError("Invalid Rainier wildlife buffers");
 for(unsigned i=0;i<na;i++){
  const struct rainier_animal *a=animals+i;
  if(!a->stride||a->stride>count||a->first>count-a->stride||a->second>count-a->stride||
     a->index>ni||a->count>ni-a->index)return SDL_SetError("Invalid Rainier wildlife span");
  if(indices)for(unsigned j=0;j<a->count;j++)if(indices[a->index+j]>=a->stride)return SDL_SetError("Invalid Rainier wildlife index");
 }
 if(scene_target(s,s->canvas)||SDL_RenderFlush(s->device))return -1;
 if(!s->rainier_program){s->rainier_program=rainier_program();if(!s->rainier_program)return -1;}
 GLint previous_program,previous_buffer,previous_indices,previous_depth;
 glGetIntegerv(GL_CURRENT_PROGRAM,&previous_program);
 glGetIntegerv(GL_ARRAY_BUFFER_BINDING,&previous_buffer);
 glGetIntegerv(GL_ELEMENT_ARRAY_BUFFER_BINDING,&previous_indices);
 glGetIntegerv(GL_RENDERBUFFER_BINDING,&previous_depth);
 glPushAttrib(GL_ALL_ATTRIB_BITS);glPushClientAttrib(GL_CLIENT_VERTEX_ARRAY_BIT);
 if(!s->rainier_buffer)glGenBuffers(1,&s->rainier_buffer);
 glBindBuffer(GL_ARRAY_BUFFER,s->rainier_buffer);
 if(vertices){glBufferData(GL_ARRAY_BUFFER,(size_t)count*7*sizeof(float),vertices,GL_STATIC_DRAW);river_bounds_build(s,vertices,terrain_count);}
 if(!s->rainier_indices)glGenBuffers(1,&s->rainier_indices);
 glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,s->rainier_indices);
 if(indices)glBufferData(GL_ELEMENT_ARRAY_BUFFER,(size_t)ni*sizeof(*indices),indices,GL_STATIC_DRAW);
 if(!s->rainier_depth)glGenRenderbuffers(1,&s->rainier_depth);
 glBindRenderbuffer(GL_RENDERBUFFER,s->rainier_depth);
 if(s->rainier_w!=s->width||s->rainier_h!=s->height){
  glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT24,s->width,s->height);
  s->rainier_w=s->width;s->rainier_h=s->height;
 }
 glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,s->rainier_depth);
 int result=0;
 if(vertices){
  GLint vb=0,ib=0;glGetBufferParameteriv(GL_ARRAY_BUFFER,GL_BUFFER_SIZE,&vb);
  glGetBufferParameteriv(GL_ELEMENT_ARRAY_BUFFER,GL_BUFFER_SIZE,&ib);
  if(vb!=(GLint)(count*7*sizeof(float))||ib!=(GLint)(ni*sizeof(unsigned))){
   SDL_SetError("Insufficient graphics memory for Rainier geometry");result=-2;goto done;
  }
 }
 if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE)
  glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT16,s->width,s->height);
 if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE){
  result=SDL_SetError("Rainier depth buffer unavailable");goto done;
 }
 glUseProgram(0);glDisable(GL_TEXTURE_2D);glDisable(GL_LIGHTING);glDisable(GL_BLEND);
 glDisable(GL_CULL_FACE);glEnable(GL_DEPTH_TEST);glDepthMask(GL_TRUE);glDepthFunc(GL_LEQUAL);
 glViewport(x,y,w,h);glEnable(GL_SCISSOR_TEST);glScissor(x,y,w,h);
 const GLfloat sky[]={.54f,.69f,.79f,1.f};
 glClearColor(sky[0],sky[1],sky[2],1);glClearDepth(1.);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
 glDisable(GL_DEPTH_TEST);glDisable(GL_FOG);
 glMatrixMode(GL_PROJECTION);glPushMatrix();glLoadIdentity();
 glMatrixMode(GL_MODELVIEW);glPushMatrix();glLoadIdentity();
 glBegin(GL_TRIANGLE_STRIP);
 glColor3f(.34f,.54f,.72f);glVertex2f(-1,-1);glVertex2f(1,-1);
 glColor3f(.76f,.84f,.87f);glVertex2f(-1,1);glVertex2f(1,1);glEnd();
 glPopMatrix();glMatrixMode(GL_PROJECTION);glPopMatrix();
 glEnable(GL_DEPTH_TEST);glUseProgram(s->rainier_program);
 glMatrixMode(GL_PROJECTION);glPushMatrix();glLoadIdentity();
 /* 58 degree vertical FOV; target texture row zero is the upper screen row. */
 double half=.2*.5543,wide=half*w/h;
 glFrustum(-wide,wide,half,-half,.2,85000.);
 glMatrixMode(GL_MODELVIEW);glPushMatrix();glLoadIdentity();
 glScalef(1,1,-1);glRotatef(-pitch*57.29578f,1,0,0);glRotatef(-yaw*57.29578f,0,1,0);
 glTranslatef(-east,-eye,-north);
 glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_COLOR_ARRAY);
 glClientActiveTexture(GL_TEXTURE0);glDisableClientState(GL_TEXTURE_COORD_ARRAY);
 glVertexPointer(3,GL_FLOAT,7*sizeof(float),0);
 glColorPointer(4,GL_FLOAT,7*sizeof(float),(const void *)(3*sizeof(float)));
 GLint blend=glGetUniformLocation(s->rainier_program,"poseBlend");
 glUniform3f(glGetUniformLocation(s->rainier_program,"picked"),picked&1,(picked>>1)&1,(picked>>2)&1);
 glUniform1f(glGetUniformLocation(s->rainier_program,"waterTime"),age);
 glActiveTexture(GL_TEXTURE0);
 if(shadows){
  if(!s->rainier_shadow)glGenTextures(1,&s->rainier_shadow);
  glBindTexture(GL_TEXTURE_2D,s->rainier_shadow);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
  glTexImage2D(GL_TEXTURE_2D,0,GL_LUMINANCE,512,512,0,GL_LUMINANCE,GL_UNSIGNED_BYTE,shadows);
 }else glBindTexture(GL_TEXTURE_2D,s->rainier_shadow);
 glUniform1i(glGetUniformLocation(s->rainier_program,"highDetail"),high);
 glUniform1i(glGetUniformLocation(s->rainier_program,"animal"),0);
 glUniform1f(blend,0.f);river_draw_land(s,terrain_count,east,eye,north,yaw,pitch,(float)w/h);
 if(high){
  glUseProgram(0);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);
  for(unsigned i=0;i<na;i++){
   const struct rainier_animal *a=animals+i;if(a->shadow<=0)continue;
   float turn=a->heading*.01745329f,c=cosf(turn),sn=sinf(turn);
   glBegin(GL_TRIANGLE_FAN);glColor4f(.055f,.075f,.08f,.48f);glVertex3f(a->x,a->y+.018f,a->z);
   glColor4f(.055f,.075f,.08f,0.f);
   for(int j=0;j<=24;j++){
    float t=j*.2617994f,u=cosf(t)*a->shadow*.70f,v=sinf(t)*a->shadow*.27f;
    float dx=c*u+sn*v+.07f*a->shadow,dz=-sn*u+c*v+.05f*a->shadow;
    glVertex3f(a->x+dx,a->y+.018f+dx*a->slope_x+dz*a->slope_z,a->z+dz);
   }
   glEnd();
  }
  glDepthMask(GL_TRUE);glDisable(GL_BLEND);glUseProgram(s->rainier_program);
 }
 glUniform1i(glGetUniformLocation(s->rainier_program,"animal"),1);
 glEnableClientState(GL_TEXTURE_COORD_ARRAY);
 for(unsigned i=0;i<na;i++){
  const struct rainier_animal *a=animals+i;
  size_t start=(size_t)a->first*7*sizeof(float);
  glVertexPointer(3,GL_FLOAT,7*sizeof(float),(const void *)start);
  glColorPointer(4,GL_FLOAT,7*sizeof(float),(const void *)(start+3*sizeof(float)));
  glTexCoordPointer(3,GL_FLOAT,7*sizeof(float),(const void *)((size_t)a->second*7*sizeof(float)));
  glUniform1f(blend,a->blend);
  glPushMatrix();glTranslatef(a->x,a->y,a->z);glRotatef(a->heading,0,1,0);
  glDrawElements(GL_TRIANGLES,(GLsizei)a->count,GL_UNSIGNED_INT,(const void *)((size_t)a->index*sizeof(unsigned)));
  glPopMatrix();
 }
 if(high)river_bloom(s,x,y,w,h);
 /* Screen-space trail markers: three berries and a pointer to the next stop. */
 glLoadIdentity();glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,w,0,h,-1,1);
 glUseProgram(0);glDisable(GL_DEPTH_TEST);
 float radius=(w<h?w:h)*.044f;
 for(int i=0;i<4;i++){
  float cx=i==3?w-radius*1.7f:radius*(1.35f+i*1.5f);
  float cy=i==3?h-radius*1.8f:radius*1.4f;
  float size=i==3?radius*1.3f:radius*.60f;
  glColor3f(.09f,.17f,.16f);
  for(int pass=0;pass<2;pass++){
   glBegin(GL_TRIANGLE_FAN);glVertex2f(cx,cy);
   for(int j=0;j<=24;j++){float a=j*6.2831853f/24.f;glVertex2f(cx+size*cosf(a),cy+size*sinf(a));}
   glEnd();
   if(i==3)break;
   size*=.76f;
   if(picked&(1<<i))glColor3f(.40f,.60f,.99f);else glColor3f(.56f,.61f,.61f);
  }
  if(i==3){
   glPushMatrix();glTranslatef(cx,cy,0);
   if(fed){
    glColor3f(.98f,.44f,.45f);
    glBegin(GL_TRIANGLE_FAN);glVertex2f(0,.76f*radius);
    for(int j=0;j<=32;j++){float a=j*6.2831853f/32.f;float sn=sinf(a);
     glVertex2f(radius*sn*sn*sn,-radius*(13*cosf(a)-5*cosf(2*a)-2*cosf(3*a)-cosf(4*a))/16.f);}
    glEnd();
   }else{
    glRotatef(direction*57.29578f,0,0,1);glColor3f(.98f,.85f,.42f);
    glBegin(GL_TRIANGLES);glVertex2f(0,-radius);glVertex2f(-radius*.68f,radius*.62f);glVertex2f(radius*.68f,radius*.62f);glEnd();
   }
   glPopMatrix();
  }
 }
 glMatrixMode(GL_MODELVIEW);
 glPopMatrix();glMatrixMode(GL_PROJECTION);glPopMatrix();
done:
 glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,0);
 glUseProgram(previous_program);glBindRenderbuffer(GL_RENDERBUFFER,previous_depth);
 glPopClientAttrib();glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,previous_indices);glBindBuffer(GL_ARRAY_BUFFER,previous_buffer);glPopAttrib();
 return result;
}
