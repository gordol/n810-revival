/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
/* Native cell-plane composition on the current Mac GPU context. */
static GLuint composition_program,composition_fbo,composition_textures[3];
static uint64_t composed_cells,composition_frames,composition_repairs;
static const char *composition_fragment=
"#version 120\n"
"uniform sampler2D atlas;uniform vec2 atlas_size;uniform vec4 rects[64],app_rects[64];uniform vec2 origins[64],app_origins[64];"
"uniform vec2 base_origin;uniform int count,mode,fill,show;uniform float opacity,shadow_size,shadow;uniform vec2 direction;"
"float risk=0.;vec3 lev=vec3(31.,63.,31.);"
"float bit(float v,float b){return mod(floor(v/b),2.);}"
"bool rgb(vec4 c){return c.w>0.&&c.w<256.;}"
"vec3 unpack(float n){return vec3(floor(n/65536.),mod(floor(n/256.),256.),mod(n,256.));}"
"float pack(vec3 v){return v.x*65536.+v.y*256.+v.z;}"
"vec3 even3(vec3 v){vec3 lo=floor(v),f=v-lo;if(any(lessThan(abs(f-.5),vec3(.0001))))risk=1.;return lo+step(vec3(.5),f)-vec3(equal(f,vec3(.5)))*vec3(equal(mod(lo,2.),vec3(0.)));}"
"float quant(vec3 v){vec3 q=clamp(v,0.,255.)*lev/255.;if(any(lessThan(abs(fract(q)-.5),vec3(.005))))risk=1.;vec3 snapped=even3(q);vec3 expanded=snapped*(255./lev);return pack(even3(expanded));}"
"vec3 role(float c){if(c==4.)return vec3(0,70,25);if(c==5.)return vec3(65,68,65);if(c==6.)return vec3(0,125,50);if(c==7.)return vec3(145,78,110);if(c==8.)return vec3(160,130,55);if(c==9.)return vec3(35,85,100);if(c==10.)return vec3(145,165,168);if(c==11.)return vec3(95,105,108);return vec3(35,110,70);}"
"bool hasrole(vec4 c){return c.w==0.&&c.z>=4.&&c.z<=12.;}"
"vec4 shade_cell(vec4 c){if(shadow<=0.)return c;vec3 f,b;if(!rgb(c)){if(!hasrole(c))return vec4(c.x,0.,14.,0.);f=role(c.z);b=vec3(10.);}else{f=unpack(c.y);b=unpack(c.z);}return vec4(c.x,quant(f*(1.-shadow)),quant(b*(1.-shadow)),1.);}"
"vec4 pane(vec4 c){vec3 f,b;if(!rgb(c)){f=hasrole(c)?role(c.z):vec3(10.);f=unpack(quant(f));b=f;}else{f=unpack(c.y);b=unpack(c.z);}return vec4(c.x,quant(f*(1.-opacity)+24.*opacity),quant(b*(1.-opacity)+24.*opacity),1.);}"
"vec4 text_cell(vec4 c){vec3 average=(unpack(c.y)+unpack(c.z))*.5;if(any(equal(fract(average),vec3(.5))))risk=1.;return vec4(c.x,quant(vec3(195,199,195)),quant(unpack(c.y)*.5+unpack(c.z)*.5),1.);}"
"vec4 terminal_cell(vec4 c,vec4 under){if(opacity>=1.)return c;if(!rgb(under)){vec3 f=hasrole(under)?role(under.z):vec3(18.);under=vec4(under.x,quant(f),quant(vec3(18.)),1.);}vec3 tint=unpack(c.w==256.?c.y:c.z),f=unpack(under.y),b=unpack(under.z);bool halfglyph=under.x==9604.||under.x==9600.;if(c.x==32.){f=even3(tint*opacity+f*(1.-opacity));b=even3(tint*opacity+b*(1.-opacity));float fc=quant(f),bc=quant(b);return vec4(halfglyph&&fc==bc?32.:under.x,fc,bc,1.);}b=halfglyph?even3((f+b)*.5):b;b=even3(tint*opacity+b*(1.-opacity));float bg=quant(b);return c.w==256.?vec4(c.x,bg,0.,256.):vec4(c.x,c.y,bg,c.w);}"
"vec4 inherit(vec4 c,vec4 under){if(c.w>0.||c.z==14.){if(c.w!=256.)return c;}vec3 f=c.w==256.?unpack(c.y):hasrole(c)?role(c.z):vec3(150,155,150);vec3 b=rgb(under)?unpack(under.z):vec3(10.);return vec4(c.x,quant(f),quant(b),1.);}"
"vec4 frame(vec4 c,vec4 under){vec3 b;if(rgb(under)){vec3 f=unpack(under.y);b=unpack(under.z);if(under.x==9604.||under.x==9600.)b=(f+b)*.5;else if(under.x==9608.)b=f;}else b=vec3(under.w==0.&&under.z==14.?8.:((under.w>0.||under.z>=4.)&&bit(c.w,16.)>0.?10.:18.));return vec4(c.x,c.y,quant(b),c.w-128.);}"
"vec4 sample_cell(vec2 p,vec2 origin){return texture2D(atlas,(origin+p+.5)/atlas_size);}"
"void main(){vec2 p=gl_TexCoord[0].xy;vec4 value=mode==0?vec4(32.,0.,13.,0.):sample_cell(p,base_origin);if(value.x<0.)value=vec4(32.,0.,13.,0.);vec4 under=value;"
"for(int j=0;j<64;j++){if(j>=count)break;int i=count-1-j;vec4 r=rects[i];vec2 pos=p-r.xy;bool inside=all(greaterThanEqual(pos,vec2(0.)))&&all(lessThan(pos,r.zw));"
"if(mode==1&&shadow>0.&&!inside&&all(greaterThanEqual(pos,direction*shadow_size))&&all(lessThan(pos,direction*shadow_size+r.zw))){value=shade_cell(value);under=shade_cell(under);}"
"if(!inside)continue;vec4 c=sample_cell(pos,origins[i]);if(c.x<0.)continue;"
"if(mode==0){if(c.w<256.&&bit(c.w,128.)>0.){if(c.x==32.)continue;c=frame(c,value);}value=c;continue;}"
"vec4 behind=value,prior=under;"
"if(c.w<256.&&bit(c.w,128.)>0.){if(c.x!=32.)value=frame(c,behind);under=fill>0?(opacity<1.?pane(prior):vec4(32.,0.,0.,0.)):prior;}"
"else if(c.w<256.&&bit(c.w,2.)>0.){value=c;under=fill>0?(opacity<1.?pane(prior):vec4(32.,0.,0.,0.)):prior;}"
"else{bool color=c.w!=0.||c.z!=0.;if(color){if(fill>0&&opacity<1.){vec4 blank=c;blank.x=32.;under=terminal_cell(blank,prior);value=c.x==32.&&!(show>0&&c.x==32.)?under:terminal_cell(c,(show>0&&c.x==32.)?behind:prior);}else{value=c;under=fill>0?vec4(32.,c.y,c.z,c.w):prior;}}"
"else if(fill==0||opacity>=1.){value=c;under=fill>0?vec4(32.,0.,0.,0.):prior;}else{under=pane(prior);value=c.x==32.?(show>0?pane(behind):under):text_cell(under);if(c.x!=32.)value.x=c.x;}"
"vec4 ar=app_rects[i];vec2 ap=p-ar.xy;if(pos.x>0.&&pos.y>0.&&pos.x<r.z-1.&&pos.y<r.w-1.&&all(greaterThanEqual(ap,vec2(0.)))&&all(lessThan(ap,ar.zw))){vec4 ac=sample_cell(ap,app_origins[i]);if(ac.x>=0.){value=ac;under=ac;if(ac.x!=9604.&&ac.x!=9600.&&ac.x!=9608.)under.x=32.;}}"
"if(fill==0){if(value.x==32.||value.x==9604.||value.x==9600.)value=behind;else if(rgb(value)){value=vec4(value.x,quant(unpack(value.y)),quant(rgb(behind)?unpack(behind.z):vec3(12.)),1.);}else value=inherit(value,behind);}"
"}}gl_FragData[0]=value;gl_FragData[1]=vec4(risk,0.,0.,0.);}";
static int composition_initialize(void){
 if(composition_program)return 0;const char *name=(const char*)glGetString(GL_RENDERER);
 if(!name||strstr(name,"Software")||strstr(name,"llvmpipe")){PyErr_SetString(PyExc_RuntimeError,"Hardware context required for GPU composition");return -1;}
 GLuint v=shader(GL_VERTEX_SHADER,vertex),f=shader(GL_FRAGMENT_SHADER,composition_fragment);if(!v||!f)return -1;
 composition_program=glCreateProgram();glAttachShader(composition_program,v);glAttachShader(composition_program,f);glLinkProgram(composition_program);glDeleteShader(v);glDeleteShader(f);
 GLint ok=0;glGetProgramiv(composition_program,GL_LINK_STATUS,&ok);if(!ok){char log[2048];glGetProgramInfoLog(composition_program,sizeof(log),NULL,log);PyErr_SetString(PyExc_RuntimeError,log);return -1;}
 glGenTextures(3,composition_textures);glGenFramebuffersEXT(1,&composition_fbo);return 0;
}
static void encode_cell(const Surface *s,size_t i,float *out){
 if(!s->valid[i]){out[0]=-1;return;}uint64_t c=s->ink[i];out[0]=(float)s->glyph[i];
 if(c>=(UINT64_C(1)<<48)){out[1]=(float)((c>>24)&0xffffff);out[2]=(float)(c&0xffffff);out[3]=(float)(c>>48);}
 else if(c>=(UINT64_C(1)<<24)){out[1]=(float)(c&0xffffff);out[2]=0;out[3]=256;}
 else{out[1]=0;out[2]=(float)c;out[3]=0;}
}
static uint64_t decode_ink(const float *v){unsigned flag=(unsigned)v[3];return flag==256?(UINT64_C(1)<<24)|(uint32_t)v[1]:flag?((uint64_t)flag<<48)|((uint64_t)(uint32_t)v[1]<<24)|(uint32_t)v[2]:(uint32_t)v[2];}
static void composition_texture(unsigned i,unsigned w,unsigned h,const float *data){glBindTexture(GL_TEXTURE_2D,composition_textures[i]);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA32F_ARB,w,h,0,GL_RGBA,GL_FLOAT,data);}
static PyObject *composition_run(PyObject *args,int mode){
 PyObject *target_obj,*base_obj=Py_None,*plans,*dirty_obj,*apps=Py_None,*styles=Py_None,*glyph_map=Py_None;int fill=1,show=0,dx=0,dy=0,ox=0,oy=0;double opacity=1,size=0,shadow=0;
 if(mode){if(!PyArg_ParseTuple(args,"OOOOidiiidd|O",&target_obj,&base_obj,&plans,&dirty_obj,&fill,&opacity,&show,&dx,&dy,&size,&shadow,&apps))return NULL;}
 else if(!PyArg_ParseTuple(args,"OOOOii|O",&target_obj,&plans,&dirty_obj,&styles,&ox,&oy,&glyph_map))return NULL;
 Surface *target=PyCapsule_GetPointer(target_obj,capsule_name);if(!target)return NULL;Surface *base=mode?PyCapsule_GetPointer(base_obj,capsule_name):NULL;if(mode&&!base)return NULL;
 Py_ssize_t count=PyTuple_Size(plans);if(count<0)return NULL;if(count>64||!isfinite(opacity)||opacity<0||opacity>1||!isfinite(shadow)||shadow<0||shadow>1||!isfinite(size)||size<0){PyErr_SetString(PyExc_ValueError,"GPU composition plan exceeds admitted bounds");return NULL;}
 Py_buffer dirty={0},mapping={0};if(PyObject_GetBuffer(dirty_obj,&dirty,PyBUF_CONTIG_RO))return NULL;
 if(dirty.len%4||(size_t)dirty.len/4>(size_t)target->w*target->h){PyBuffer_Release(&dirty);PyErr_SetString(PyExc_ValueError,"Invalid GPU composition indices");return NULL;}
 if(glyph_map!=Py_None&&PyObject_GetBuffer(glyph_map,&mapping,PyBUF_CONTIG_RO)){PyBuffer_Release(&dirty);return NULL;}
 Layer layers[64]={0},application[64]={0};Surface *sources[129]={0};float rects[256]={0},app_rects[256]={0},origins[128]={0},app_origins[128]={0},base_origin[2]={0};unsigned sx[129]={0},sy[129]={0},ns=0,cursor_x=0,cursor_y=0,row_h=0,atlas_w=2048;
 if(base){if(base==target||base->w!=target->w||base->h!=target->h){PyErr_SetString(PyExc_ValueError,"GPU base alias/dimension mismatch");goto fail_inputs;}sources[ns++]=base;}
 for(Py_ssize_t i=0;i<count;i++){
  PyObject *entry=PyTuple_GetItem(plans,i),*plane;int x,y;
  if(!entry||!PyArg_ParseTuple(entry,"Oii",&plane,&x,&y))goto fail_inputs;Surface *p=PyCapsule_GetPointer(plane,capsule_name);if(!p)goto fail_inputs;if(p==target){PyErr_SetString(PyExc_ValueError,"GPU input aliases output");goto fail_inputs;}
  layers[i]=(Layer){p,x,y};rects[i*4]=x;rects[i*4+1]=y;rects[i*4+2]=p->w;rects[i*4+3]=p->h;sources[ns++]=p;
  if(apps!=Py_None){if(!PyTuple_Check(apps)||PyTuple_Size(apps)!=count){PyErr_SetString(PyExc_ValueError,"GPU app plans mismatch");goto fail_inputs;}PyObject *app=PyTuple_GetItem(apps,i);
   if(app!=Py_None){if(!PyArg_ParseTuple(app,"Oii",&plane,&x,&y))goto fail_inputs;p=PyCapsule_GetPointer(plane,capsule_name);if(!p)goto fail_inputs;if(p==target){PyErr_SetString(PyExc_ValueError,"GPU app aliases output");goto fail_inputs;}application[i]=(Layer){p,x,y};app_rects[i*4]=x;app_rects[i*4+1]=y;app_rects[i*4+2]=p->w;app_rects[i*4+3]=p->h;sources[ns++]=p;}
  }
 }
 for(unsigned i=0;i<ns;i++){
  Surface *p=sources[i];if(p->w>atlas_w||!p->w||!p->h){PyErr_SetString(PyExc_ValueError,"GPU source size exceeds admitted atlas");goto fail_inputs;}
  if(cursor_x+p->w>atlas_w){cursor_y+=row_h;cursor_x=0;row_h=0;}sx[i]=cursor_x;sy[i]=cursor_y;cursor_x+=p->w;if(row_h<p->h)row_h=p->h;
 }
 unsigned atlas_h=cursor_y+row_h;if(!atlas_h)atlas_h=1;if(atlas_h>16384){PyErr_SetString(PyExc_ValueError,"GPU layer atlas exceeds device bound");goto fail_inputs;}
 size_t nd=(size_t)dirty.len/4;if(!nd){PyBuffer_Release(&dirty);if(mapping.obj)PyBuffer_Release(&mapping);return Py_BuildValue("(IKy#)",0,(unsigned long long)0,"",(Py_ssize_t)0);}
 const uint32_t *indices=dirty.buf;for(size_t i=0;i<nd;i++)if(indices[i]>=(size_t)target->w*target->h){PyErr_SetString(PyExc_ValueError,"GPU composition index outside viewport");goto fail_inputs;}
 float *atlas=calloc((size_t)atlas_w*atlas_h*4,sizeof(float)),*vertices=malloc(nd*4*sizeof(float));unsigned outw=nd<1024?(unsigned)nd:1024,outh=(unsigned)((nd+outw-1)/outw);float *readback=malloc((size_t)outw*outh*8*sizeof(float));uint32_t *uncertain=malloc(nd*4);
 if(!atlas||!vertices||!readback||!uncertain){free(atlas);free(vertices);free(readback);free(uncertain);PyErr_NoMemory();goto fail_inputs;}
 for(unsigned i=0;i<ns;i++)for(unsigned y=0;y<sources[i]->h;y++)for(unsigned x=0;x<sources[i]->w;x++)encode_cell(sources[i],(size_t)y*sources[i]->w+x,atlas+((size_t)(sy[i]+y)*atlas_w+sx[i]+x)*4);
 unsigned at=0;if(base){base_origin[0]=sx[at];base_origin[1]=sy[at++];}
 for(Py_ssize_t i=0;i<count;i++){origins[i*2]=sx[at];origins[i*2+1]=sy[at++];if(application[i].plane){app_origins[i*2]=sx[at];app_origins[i*2+1]=sy[at++];}}
 for(size_t i=0;i<nd;i++){vertices[i*4]=(float)(i%outw)+.5f;vertices[i*4+1]=(float)(i/outw)+.5f;vertices[i*4+2]=(float)(indices[i]%target->w);vertices[i*4+3]=(float)(indices[i]/target->w);}
 GLint old_fbo,old_program,old_active;glGetIntegerv(GL_FRAMEBUFFER_BINDING_EXT,&old_fbo);glGetIntegerv(GL_CURRENT_PROGRAM,&old_program);glGetIntegerv(GL_ACTIVE_TEXTURE,&old_active);glPushAttrib(GL_ALL_ATTRIB_BITS);glPushClientAttrib(GL_CLIENT_ALL_ATTRIB_BITS);
 glMatrixMode(GL_PROJECTION);glPushMatrix();glLoadIdentity();glOrtho(0,outw,0,outh,-1,1);glMatrixMode(GL_MODELVIEW);glPushMatrix();glLoadIdentity();
 int error=composition_initialize();if(error)goto restore_compose;
 glUseProgram(composition_program);glBindFramebufferEXT(GL_FRAMEBUFFER_EXT,composition_fbo);glActiveTexture(GL_TEXTURE0);composition_texture(0,atlas_w,atlas_h,atlas);composition_texture(1,outw,outh,NULL);composition_texture(2,outw,outh,NULL);
 glFramebufferTexture2DEXT(GL_FRAMEBUFFER_EXT,GL_COLOR_ATTACHMENT0_EXT,GL_TEXTURE_2D,composition_textures[1],0);glFramebufferTexture2DEXT(GL_FRAMEBUFFER_EXT,GL_COLOR_ATTACHMENT1_EXT,GL_TEXTURE_2D,composition_textures[2],0);GLenum bufs[2]={GL_COLOR_ATTACHMENT0_EXT,GL_COLOR_ATTACHMENT1_EXT};glDrawBuffers(2,bufs);glReadBuffer(GL_COLOR_ATTACHMENT0_EXT);
 if(glCheckFramebufferStatusEXT(GL_FRAMEBUFFER_EXT)!=GL_FRAMEBUFFER_COMPLETE_EXT){PyErr_SetString(PyExc_RuntimeError,"GPU composition targets unavailable");error=-1;goto restore_compose;}
 glBindTexture(GL_TEXTURE_2D,composition_textures[0]);glViewport(0,0,outw,outh);glDisable(GL_DEPTH_TEST);glDisable(GL_LIGHTING);glDisable(GL_BLEND);glDisable(GL_VERTEX_PROGRAM_ARB);glDisable(GL_SCISSOR_TEST);glDisable(GL_POINT_SMOOTH);glDisable(GL_DITHER);glPointSize(1);
 glUniform1i(glGetUniformLocation(composition_program,"atlas"),0);glUniform2f(glGetUniformLocation(composition_program,"atlas_size"),atlas_w,atlas_h);glUniform1i(glGetUniformLocation(composition_program,"mode"),mode);glUniform1i(glGetUniformLocation(composition_program,"count"),(GLint)count);glUniform1i(glGetUniformLocation(composition_program,"fill"),fill);glUniform1i(glGetUniformLocation(composition_program,"show"),show);glUniform1f(glGetUniformLocation(composition_program,"opacity"),(float)opacity);glUniform1f(glGetUniformLocation(composition_program,"shadow_size"),(float)size);glUniform1f(glGetUniformLocation(composition_program,"shadow"),(float)shadow);glUniform2f(glGetUniformLocation(composition_program,"direction"),dx,dy);
 glUniform2fv(glGetUniformLocation(composition_program,"base_origin"),1,base_origin);glUniform4fv(glGetUniformLocation(composition_program,"rects"),64,rects);glUniform4fv(glGetUniformLocation(composition_program,"app_rects"),64,app_rects);glUniform2fv(glGetUniformLocation(composition_program,"origins"),64,origins);glUniform2fv(glGetUniformLocation(composition_program,"app_origins"),64,app_origins);
 glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_TEXTURE_COORD_ARRAY);glDisableClientState(GL_COLOR_ARRAY);glDisableClientState(GL_NORMAL_ARRAY);glVertexPointer(2,GL_FLOAT,4*sizeof(float),vertices);glTexCoordPointer(2,GL_FLOAT,4*sizeof(float),vertices+2);glDrawArrays(GL_POINTS,0,(GLsizei)nd);
 glReadBuffer(GL_COLOR_ATTACHMENT0_EXT);glReadPixels(0,0,outw,outh,GL_RGBA,GL_FLOAT,readback);glReadBuffer(GL_COLOR_ATTACHMENT1_EXT);glReadPixels(0,0,outw,outh,GL_RGBA,GL_FLOAT,readback+(size_t)outw*outh*4);
 if(glGetError()!=GL_NO_ERROR){PyErr_SetString(PyExc_RuntimeError,"GPU composition failed; no CPU fallback");error=-1;goto restore_compose;}
restore_compose:
 glUseProgram((GLuint)old_program);glBindFramebufferEXT(GL_FRAMEBUFFER_EXT,(GLuint)old_fbo);glActiveTexture((GLenum)old_active);glMatrixMode(GL_MODELVIEW);glPopMatrix();glMatrixMode(GL_PROJECTION);glPopMatrix();glPopClientAttrib();glPopAttrib();
 PyObject *answer=NULL;
 if(!error){size_t changed=0,repair_count=0;for(size_t i=0;i<nd;i++){
  unsigned glyph=(unsigned)readback[i*4];uint64_t color=decode_ink(readback+i*4);
  if(mapping.obj)glyph=cw_mapped_glyph(glyph,mapping.buf,(size_t)mapping.len/8);
  unsigned index=indices[i];if(!target->valid[index]||target->glyph[index]!=glyph||target->ink[index]!=color)changed++;
  cw_set(target,index,glyph,color,1);if(readback[(size_t)outw*outh*4+i*4]>.5f)uncertain[repair_count++]=index;
 }
 composition_frames++;composed_cells+=nd;composition_repairs+=repair_count;
 answer=Py_BuildValue("(KKy#)",(unsigned long long)changed,(unsigned long long)nd,(char*)uncertain,(Py_ssize_t)repair_count*4);
 }
 free(atlas);free(vertices);free(readback);free(uncertain);PyBuffer_Release(&dirty);if(mapping.obj)PyBuffer_Release(&mapping);return answer;
fail_inputs:
 PyBuffer_Release(&dirty);if(mapping.obj)PyBuffer_Release(&mapping);return NULL;
}
static PyObject *gpu_blend(PyObject *self,PyObject *args){(void)self;return composition_run(args,1);}
static PyObject *gpu_compose(PyObject *self,PyObject *args){(void)self;return composition_run(args,0);}
