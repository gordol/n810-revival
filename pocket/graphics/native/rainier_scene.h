/* Static world-space terrain and vegetation. Use the SDL OpenGL canvas
 * directly, preserving the renderer state used by subsequent UI drawing. */
static GLuint rainier_program(void){
 const char *vs="#version 120\n"
  "varying vec3 pos;varying vec4 tint;varying float distanceToEye;"
  "uniform float poseBlend;uniform int skyPass;"
  "void main(){if(skyPass!=0){pos=gl_Vertex.xyz;distanceToEye=0.;tint=vec4(1.);gl_Position=gl_Vertex;return;}pos=mix(gl_Vertex.xyz,gl_MultiTexCoord0.xyz,poseBlend);tint=gl_Color;"
  "vec4 eye=gl_ModelViewMatrix*vec4(pos,1.);"
  "distanceToEye=length(eye.xyz);gl_Position=gl_ProjectionMatrix*eye;}";
 const char *fs="#version 120\n"
  "varying vec3 pos;varying vec4 tint;varying float distanceToEye;"
  "uniform vec4 supplies;uniform int camp;uniform int season;uniform float originY;uniform float hazeDensity;uniform float waterTime;uniform vec3 picked;uniform int highDetail;uniform int animal;uniform sampler2D forestShade;"
  "float hash(vec2 p){vec3 q=fract(vec3(p.xyx)*.1031);q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}"
  "float noise(vec2 p){vec2 i=floor(p),u=fract(p);u=u*u*(3.-2.*u);"
  "return mix(mix(hash(i),hash(i+vec2(1,0)),u.x),mix(hash(i+vec2(0,1)),hash(i+1.),u.x),u.y);}"
  "uniform vec3 waterEye;uniform vec2 shadeCenter;uniform vec2 shadowStep;uniform int regional;uniform int skyPass;uniform vec4 skyCamera;uniform float daylight;uniform float overcast;"
  "vec3 horizon(){return mix(vec3(.095,.13,.20),mix(vec3(.87,.58,.43),vec3(.68,.80,.86),smoothstep(.35,.9,daylight)),daylight);}"
  "vec3 skyDirection(){vec2 uv=vec2(pos.x*skyCamera.z,-pos.y)*skyCamera.w;"
  "float cp=cos(skyCamera.y),sp=sin(skyCamera.y);float f=cp+uv.y*sp;"
  "return normalize(vec3(uv.x*cos(skyCamera.x)+f*sin(skyCamera.x),uv.y*cp-sp,f*cos(skyCamera.x)-uv.x*sin(skyCamera.x)));}"
  "vec3 skyColor(vec3 dir){"
  "float alt=max(0.,dir.y);vec3 col=mix(horizon(),mix(vec3(.012,.023,.064),vec3(.24,.48,.73),daylight),smoothstep(0.,.65,alt));"
  "vec2 dome=dir.xz/(1.+dir.y+.001);vec2 star=dome*300.;float seed=hash(floor(star));"
  "float light=1.-smoothstep(.04,.33,length(fract(star)-.5));"
  "col+=vec3(.79,.86,1.)*light*step(.975,seed)*(1.-smoothstep(.08,.38,daylight))*smoothstep(.01,.18,alt);"
  "vec2 p=dir.xz/max(.075,alt)*2.1+vec2(waterTime*.013,waterTime*.002);"
  "float n=.57*noise(p)+.30*noise(2.1*p)+.13*noise(4.4*p);"
  "float cloud=smoothstep(.52-.15*overcast,.78-.12*overcast,n)*smoothstep(.015,.14,alt);"
  "return mix(col,mix(vec3(.13,.16,.22),vec3(.87,.88,.86),daylight),cloud);}"
  "vec3 reflectedBank(vec3 ray){vec3 sky=skyColor(ray);"
  // The valley canopy texture stores crown heights at the actual tree sites.
  // Trace a short ray above the water plane; the far field uses the sky.
  "for(int i=1;i<=16;i++){float d=float(i)*(.8+.21*float(i));vec3 p=pos+d*ray;"
  "vec2 uv=p.xz/2048.+.5;if(max(abs(uv.x-.5),abs(uv.y-.5))>=.5)break;"
  "float crown=texture2D(forestShade,uv).r*85.;float hit=smoothstep(.0,1.4,crown-(p.y-pos.y));"
  "if(hit>.05){vec3 needles=vec3(.12,.24,.18)*(.74+.35*noise(p.xz*.35))*(.24+.76*daylight);"
  "return mix(sky,needles,hit);}}return sky;}"
  "void main(){if(skyPass!=0){gl_FragColor=vec4(skyColor(skyDirection()),1.);return;}if(tint.a>.85 && tint.a<.89 && (season==1 || season==2 || (season==3 && tint.a<.87)))discard;if((abs(tint.a-.60)<.004 && supplies.x>.5)||(abs(tint.a-.61)<.004 && supplies.y>.5)||(abs(tint.a-.62)<.004 && supplies.z>.5)||(abs(tint.a-.63)<.004 && supplies.w<.5))discard;if((abs(tint.a-.57)<.005 && camp<1)||(abs(tint.a-.59)<.005 && camp<2))discard;if((abs(tint.a-.08)<.01 && picked.x>.5)||(abs(tint.a-.13)<.01 && picked.y>.5)||(abs(tint.a-.18)<.01 && picked.z>.5))discard;float alpha=1.;float reflection=0.;vec3 reflected=vec3(0.);float castShade=0.;vec3 col=tint.rgb;if(tint.a>.9){vec2 p=pos.xz;"
  "float broad=noise(p*.015);float detail=(noise(p*.64)-.5)*(1.-smoothstep(80.,600.,distanceToEye));"
  "col*=.80+.40*broad+.30*detail;col+=vec3(.032,.024,-.013)*broad;"
  "if(highDetail!=0){float grit=noise(p*11.)-.5;float moss=noise(p*.18);"
  "col+=vec3(.075,.055,.026)*moss;col+=grit*vec3(.041,.037,.024)*(1.-smoothstep(6.,38.,distanceToEye));"
  "}"
  "if(regional!=0){float elev=pos.y+originY;float line=1920.+100.*sin(p.x*.0017)+55.*cos(p.y*.0021);"
  "float meadow=smoothstep(1480.,1650.,elev)*(1.-smoothstep(2100.,2380.,elev));"
  "float drift=.65*noise(p*.115)+.35*noise(p*.38);float blades=noise(vec2(p.x*2.7,p.y*7.1));"
  "vec3 turf=mix(vec3(.18,.25,.12),vec3(.42,.45,.25),drift);"
  "if(season==1)turf=mix(vec3(.31,.19,.16),vec3(.55,.43,.23),drift);"
  "col=mix(col,turf*(.79+.41*blades),.72*meadow*(1.-smoothstep(90.,380.,distanceToEye)));"
  "float stand=(1.-smoothstep(line-230.,line,elev))*smoothstep(.26,.69,noise(p*.018));"
  "col=mix(col,col*vec3(.48,.71,.54),stand*smoothstep(65.,170.,distanceToEye));}"
  "float footprint=regional!=0?512.:2048.;vec2 uv=(p-shadeCenter)/footprint+.5;"
  "if(daylight>.12 && distanceToEye<340. && max(abs(uv.x-.5),abs(uv.y-.5))<.46){"
  "vec3 n=cross(dFdx(pos),dFdy(pos));float slope=abs(n.y)>.001?dot(n.xz/n.y,shadowStep):0.;"
  "float shade=0.;for(int i=0;i<8;i++){float level=.75+float(i)*(1.5+.95*float(i));"
  "float canopy=texture2D(forestShade,uv-shadowStep*level/footprint).r*85.;"
  "shade=max(shade,smoothstep(-.6,.6,canopy-level*(1.-clamp(slope,-1.,.85)))*step(.1,canopy));}"
  "float fade=(1.-smoothstep(175.,340.,distanceToEye))*smoothstep(.12,.62,daylight)*(1.-.68*overcast);"
  "castShade=shade*fade;}}"
  "if(tint.a>.935 && tint.a<.97){float grains=noise(pos.xz*24.);float stone=noise(pos.xz*6.);"
  "float lensing=sin(7.*pos.z+3.*sin(5.*pos.x+waterTime*.9)+waterTime)*sin(5.*pos.x+1.7*pos.z-waterTime*.8);"
  "col*=.84+.20*stone+.15*grains;col+=vec3(.10,.12,.095)*smoothstep(.60,.95,lensing)*daylight;}"
  "if(highDetail!=0 && tint.a>.46 && tint.a<.50){float bark=noise(vec2((pos.x+pos.z)*21.,pos.y*2.6));col*=.68+.6*bark;}"
  "if(highDetail!=0 && tint.a>.06 && tint.a<.20){vec3 n=normalize(cross(dFdx(pos),dFdy(pos)));"
  "float wax=pow(abs(dot(n,normalize(vec3(-.42,.79,-.44)))),14.);col+=vec3(.28,.34,.43)*wax;}"
  // Distant crown vertices encode lateral position in red and height in alpha.
  "if(regional!=0 && tint.a>.539 && tint.a<.561){float h=(tint.a-.54)*50.;"
  "float whorl=fract(h*7.+.18*sin(pos.x+pos.z));float side=abs(2.*tint.r-1.);"
  "if(side>(1.-h)*(.68+.75*whorl)+.08)discard;"
  "float light=.78+.27*whorl+.16*noise(pos.xz*1.4);col=vec3(.55*tint.g,tint.g,tint.b)*light;}"
  "if(regional!=0 && tint.a>=.499 && tint.a<.516){"
  "float sprays=noise(pos.xz*4.+pos.y*vec2(1.4,3.6));float needles=noise(pos.xz*15.+pos.y*5.);"
  "if(tint.a>.509 && sprays+.21*needles<.44)discard;"
  "col*=.71+.48*sprays+.16*needles;}"
  "if(regional!=0 && abs(tint.a-.815)<.003){if(season==2)discard;if(season==1)col*=vec3(1.35,.98,.70);}"
  "if(regional!=0 && abs(tint.a-.83)<.005){float drift=.65*noise(pos.xz*.13)+.35*noise(pos.xz*.46);"
  "if(season==1){vec3 leaves=mix(vec3(.30,.085,.13),vec3(.69,.16,.20),smoothstep(.26,.54,drift));"
  "col=mix(leaves,vec3(.85,.54,.13),smoothstep(.55,.74,drift))*(.70+.66*tint.g);}"
  "if(season==2)col=mix(col,vec3(.77,.82,.83),.76);}"
  "if(tint.a>.65 && tint.a<.85){float seams=noise(vec2(pos.x*.006,pos.z*.036+sin(pos.x*.007)));"
  "col*=1.-.25*smoothstep(.60,.78,seams);}"
  "if(tint.a>.52 && tint.a<.54){float gravel=noise(pos.xz*3.6);"
  "float grains=noise(pos.xz*16.)-.5;col*=.75+.44*gravel+.20*grains*(1.-smoothstep(6.,22.,distanceToEye));}"
  "if(tint.a>.25 && tint.a<.45){vec2 flow=vec2(tint.r*12.-6.,tint.g*4096.-waterTime*.95);"
  "float current=noise(flow*vec2(.8,.38));float riffle=sin(flow.y*5.3+4.*current+flow.x*.8);"
  "col=mix(vec3(.105,.285,.275),vec3(.25,.44,.43),current);"
  "float facing=abs(normalize(waterEye-pos).y);float calm=1.-smoothstep(2.,10.,length((pos.xz-vec2(15.,8.))*vec2(1.,.7)));"
  "alpha=mix(.23,.095,calm)+.12*overcast+.08*(1.-calm)*smoothstep(.73,.99,riffle);"
  "float chop=(.018+.028*overcast)*(1.-.65*calm);"
  "vec3 normal=normalize(vec3(chop*(riffle+.6*sin(3.*flow.x+2.*current)),1.,chop*cos(3.8*flow.y+5.*current)));"
  "vec3 ray=reflect(normalize(pos-waterEye),normal);ray.y=max(.015,ray.y);"
  "reflected=reflectedBank(normalize(ray));float fresnel=.018+.94*pow(1.-facing,mix(3.5,7.,calm));"
  "alpha=alpha+(1.-alpha)*fresnel;reflection=fresnel/alpha;"
  "float fade=1.-smoothstep(25.,110.,distanceToEye);"
  "col+=vec3(.17,.21,.20)*fade*smoothstep(.82,.99,riffle)*smoothstep(.46,.80,current);}"
  "if(highDetail!=0 && animal!=0 && distanceToEye<16.){float strands=noise(vec2((pos.x+.3*pos.z)*55.,(pos.y+.15*pos.x)*245.));"
  "col*=1.+.20*(strands-.5)*(1.-smoothstep(3.,16.,distanceToEye));}"
  "if(tint.a>.9 && animal==0){float elev=pos.y+originY;"
  "if(season==1)col=mix(col,col*vec3(1.28,1.02,.76),.65);"
  "if(season==2 || season==3){float line=season==2?520.:1600.;"
  "float cover=smoothstep(line-95.,line+150.,elev+110.*noise(pos.xz*.045));"
  "col=mix(col,vec3(.79,.85,.88),cover*.88);}}"
  "if(regional!=0 && tint.a>.99 && pos.y+originY>2350.){"
  "vec3 n=normalize(cross(dFdx(pos),dFdy(pos)));float elev=pos.y+originY;"
  "float seams=.59*noise(pos.xz*.013)+.28*noise(pos.xz*.043)+.13*noise(pos.xz*.12);"
  "float line=smoothstep(2450.,3150.,elev);float retention=abs(n.y)+.48*(seams-.5)+.15*line;"
  "vec3 rock=mix(vec3(.21,.22,.27),vec3(.48,.43,.42),seams);"
  "vec3 snow=mix(vec3(.62,.71,.84),vec3(.98,.985,.99),clamp(.5+.5*dot(n*sign(n.y),normalize(vec3(-.5,.6,.4))),0.,1.));"
  "col=mix(col,mix(rock,snow,smoothstep(.81,.92,retention)),smoothstep(2350.,2750.,elev));}"
  "col*=mix(vec3(1.),vec3(.52,.63,.72),castShade);"
  "float haze=1.-exp(-distanceToEye*hazeDensity);vec3 lit=col*mix(vec3(.24,.32,.47),vec3(1.),daylight);gl_FragColor=vec4(mix(mix(lit,reflected,reflection),horizon(),haze),alpha);}";
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

static void river_draw_land(struct gpu_scene *s,unsigned count,unsigned skip,float x,float y,float z,float yaw,float pitch,float aspect){
 if(!s->river_blocks){glDrawArrays(GL_TRIANGLES,(GLint)skip,(GLsizei)(count-skip));return;}
 float sy=sinf(yaw),cy=cosf(yaw),sp=sinf(pitch),cp=cosf(pitch);
 float ty=.5543f,tx=ty*aspect,kx=sqrtf(1+tx*tx),ky=sqrtf(1+ty*ty);
 unsigned start=skip;
 for(unsigned first=skip/RIVER_BATCH*RIVER_BATCH;first<count;first+=RIVER_BATCH){
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

static void river_hiker_band(float bottom,float top,float base,float rim,float r,float g,float b){
 glBegin(GL_QUAD_STRIP);
 for(int j=0;j<=8;j++){
  float a=j*.78539816f,x=cosf(a),z=sinf(a);
  float light=.78f+.16f*x-.06f*z;
  glColor3f(r*light,g*light,b*light);
  glVertex3f(x*base,bottom,z*base);glVertex3f(x*rim,top,z*rim);
 }
 glEnd();
}

int pocket_scene_rainier(void *ptr,int x,int y,int w,int h,const float *vertices,unsigned count,
                         unsigned terrain_count,const unsigned *indices,unsigned ni,
                         const struct rainier_animal *animals,unsigned na,
                         float east,float eye,float north,float yaw,float pitch,float age,int picked,float direction,int fed,int high,const unsigned char *shadows,const float *hikers,unsigned nh,const float *marker,const float *ripple,int lens,unsigned char *photo,int photo_animal,float focal,int camp,int season,int weather,float originY,float daylight,float sun_angle,float center_x,float center_z,const float *grove,unsigned grove_count,unsigned water_count){
 struct gpu_scene *s=ptr;
 if(!s||w<1||h<1||count<3||count>2000000||(!vertices&&!s->rainier_buffer))
  return SDL_SetError("Invalid Rainier scene");
 if(water_count>terrain_count||grove_count>250000||nh>7||(nh&&!hikers)||terrain_count>count||ni>2000000||na>64||(!animals&&na)||
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
 glUseProgram(s->rainier_program);
 GLint sky_pass=glGetUniformLocation(s->rainier_program,"skyPass");
 glUniform1i(sky_pass,1);
 glUniform4f(glGetUniformLocation(s->rainier_program,"skyCamera"),yaw,pitch,(float)w/h,.5543f/fmaxf(1.f,focal));
 glUniform1f(glGetUniformLocation(s->rainier_program,"daylight"),daylight);
 glUniform1f(glGetUniformLocation(s->rainier_program,"overcast"),weather?1.f:0.f);
 glUniform1f(glGetUniformLocation(s->rainier_program,"waterTime"),age);
 glBegin(GL_TRIANGLE_STRIP);glVertex2f(-1,-1);glVertex2f(1,-1);glVertex2f(-1,1);glVertex2f(1,1);glEnd();
 glUniform1i(sky_pass,0);
 glPopMatrix();glMatrixMode(GL_PROJECTION);glPopMatrix();
 glEnable(GL_DEPTH_TEST);glUseProgram(s->rainier_program);
 glMatrixMode(GL_PROJECTION);glPushMatrix();glLoadIdentity();
 /* 58 degree vertical FOV; target texture row zero is the upper screen row. */
 double half=.2*.5543/fmaxf(1.f,focal),wide=half*w/h;
 glFrustum(-wide,wide,half,-half,.2,85000.);
 glMatrixMode(GL_MODELVIEW);glPushMatrix();glLoadIdentity();
 glScalef(1,1,-1);glRotatef(-pitch*57.29578f,1,0,0);glRotatef(-yaw*57.29578f,0,1,0);
 glTranslatef(-east,-eye,-north);
 glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_COLOR_ARRAY);
 glClientActiveTexture(GL_TEXTURE0);glDisableClientState(GL_TEXTURE_COORD_ARRAY);
 glVertexPointer(3,GL_FLOAT,7*sizeof(float),0);
 glColorPointer(4,GL_FLOAT,7*sizeof(float),(const void *)(3*sizeof(float)));
 GLint blend=glGetUniformLocation(s->rainier_program,"poseBlend");
 glUniform1f(glGetUniformLocation(s->rainier_program,"hazeDensity"),(lens<0?.000055f:.00042f)*(weather?5.f:1.f));
 glUniform1i(glGetUniformLocation(s->rainier_program,"camp"),camp&3);
 glUniform4f(glGetUniformLocation(s->rainier_program,"supplies"),(camp>>2)&1,(camp>>3)&1,(camp>>4)&1,(camp>>5)&1);
 glUniform1i(glGetUniformLocation(s->rainier_program,"season"),season);
 glUniform1f(glGetUniformLocation(s->rainier_program,"originY"),originY);
 glUniform3f(glGetUniformLocation(s->rainier_program,"picked"),picked&1,(picked>>1)&1,(picked>>2)&1);
 glUniform1f(glGetUniformLocation(s->rainier_program,"waterTime"),age);
 glActiveTexture(GL_TEXTURE0);
 float stretch=.55f+2.3f*(1.f-daylight);
 glUniform2f(glGetUniformLocation(s->rainier_program,"shadowStep"),cosf(sun_angle)*stretch,sinf(sun_angle)*stretch);
 glUniform2f(glGetUniformLocation(s->rainier_program,"shadeCenter"),center_x,center_z);
 glUniform1i(glGetUniformLocation(s->rainier_program,"regional"),lens<0);
 if(shadows){
  if(!s->rainier_shadow)glGenTextures(1,&s->rainier_shadow);
  glBindTexture(GL_TEXTURE_2D,s->rainier_shadow);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
  int canopy_size=lens<0?512:1024;
  glTexImage2D(GL_TEXTURE_2D,0,GL_LUMINANCE,canopy_size,canopy_size,0,GL_LUMINANCE,GL_UNSIGNED_BYTE,shadows);
 }else glBindTexture(GL_TEXTURE_2D,s->rainier_shadow);
 glUniform1i(glGetUniformLocation(s->rainier_program,"highDetail"),high);
 glUniform1i(glGetUniformLocation(s->rainier_program,"animal"),0);
 glUniform1f(blend,0.f);river_draw_land(s,terrain_count,water_count,east,eye,north,yaw,pitch,(float)w/h);
 if(grove_count){
  if(!s->rainier_grove)glGenBuffers(1,&s->rainier_grove);
  glBindBuffer(GL_ARRAY_BUFFER,s->rainier_grove);
  if(grove)glBufferData(GL_ARRAY_BUFFER,(size_t)grove_count*7*sizeof(float),grove,GL_DYNAMIC_DRAW);
  glVertexPointer(3,GL_FLOAT,7*sizeof(float),0);
  glColorPointer(4,GL_FLOAT,7*sizeof(float),(const void *)(3*sizeof(float)));
  glDrawArrays(GL_TRIANGLES,0,(GLsizei)grove_count);
  glBindBuffer(GL_ARRAY_BUFFER,s->rainier_buffer);
 }
 if(high){
  glUseProgram(0);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);
  for(unsigned i=0;i<na;i++){
   const struct rainier_animal *a=animals+i;if(a->shadow<=0)continue;
   float turn=a->heading*.01745329f,c=cosf(turn),sn=sinf(turn);
   glBegin(GL_TRIANGLE_FAN);glColor4f(.055f,.075f,.08f,.48f*daylight*(weather?.4f:1.f));glVertex3f(a->x,a->y+.018f,a->z);
   glColor4f(.055f,.075f,.08f,0.f);
   for(int j=0;j<=24;j++){
    float t=j*.2617994f,u=cosf(t)*a->shadow*.70f,v=sinf(t)*a->shadow*.27f;
    float dx=c*u+sn*v+cosf(sun_angle)*.22f*stretch*a->shadow,dz=-sn*u+c*v+sinf(sun_angle)*.22f*stretch*a->shadow;
    glVertex3f(a->x+dx,a->y+.018f+dx*a->slope_x+dz*a->slope_z,a->z+dz);
   }
   glEnd();
  }
  glDepthMask(GL_TRUE);glDisable(GL_BLEND);glUseProgram(s->rainier_program);
 }
 glUniform1i(glGetUniformLocation(s->rainier_program,"animal"),1);
 glEnableClientState(GL_TEXTURE_COORD_ARRAY);
 GLuint photo_query=0;
 if(photo && photo_animal>=0 && (unsigned)photo_animal<na)glGenQueries(1,&photo_query);
 for(unsigned i=0;i<na;i++){
  const struct rainier_animal *a=animals+i;
  size_t start=(size_t)a->first*7*sizeof(float);
  glVertexPointer(3,GL_FLOAT,7*sizeof(float),(const void *)start);
  glColorPointer(4,GL_FLOAT,7*sizeof(float),(const void *)(start+3*sizeof(float)));
  glTexCoordPointer(3,GL_FLOAT,7*sizeof(float),(const void *)((size_t)a->second*7*sizeof(float)));
  glUniform1f(blend,a->blend);
  glPushMatrix();glTranslatef(a->x,a->y,a->z);glRotatef(a->heading,0,1,0);
  if(photo_query && (int)i==photo_animal)glBeginQuery(GL_SAMPLES_PASSED,photo_query);
  glDrawElements(GL_TRIANGLES,(GLsizei)a->count,GL_UNSIGNED_INT,(const void *)((size_t)a->index*sizeof(unsigned)));
  if(photo_query && (int)i==photo_animal)glEndQuery(GL_SAMPLES_PASSED);
  glPopMatrix();
 }
 /* Small rain jackets and knit caps stand out against the dark conifers. */
 glUseProgram(0);
 static const float coats[][3]={{.93f,.47f,.12f},{.12f,.66f,.67f},{.75f,.28f,.40f},
  {.42f,.48f,.81f},{.85f,.67f,.18f},{.50f,.63f,.27f},{.68f,.38f,.65f}};
 for(unsigned i=0;i<nh;i++){
  const float *p=hikers+i*3,*coat=coats[i];
  glPushMatrix();glTranslatef(p[0],p[1],p[2]);
  for(int leg=-1;leg<=1;leg+=2){
   glPushMatrix();glTranslatef(leg*.10f,0,0);
   river_hiker_band(.02f,.52f,.085f,.09f,.13f,.16f,.19f);
   glPopMatrix();
  }
  river_hiker_band(.48f,.94f,.22f,.24f,coat[0],coat[1],coat[2]);
  river_hiker_band(.94f,1.10f,.24f,.11f,coat[0],coat[1],coat[2]);
  river_hiker_band(1.09f,1.32f,.12f,.14f,.63f,.44f,.32f);
  river_hiker_band(1.29f,1.37f,.16f,.15f,.89f,.83f,.65f);
  river_hiker_band(1.37f,1.45f,.15f,.025f,.79f,.74f,.58f);
  glPopMatrix();
 }
 /* Blend the river over opaque bed, fish and banks. Depth testing leaves
    a breaching fish above the surface and hides water behind shore rocks. */
 if(water_count){
  glUseProgram(s->rainier_program);
  glUniform1i(glGetUniformLocation(s->rainier_program,"animal"),0);
  glUniform3f(glGetUniformLocation(s->rainier_program,"waterEye"),east,eye,north);
  glUniform1f(blend,0.f);glDisableClientState(GL_TEXTURE_COORD_ARRAY);
  glVertexPointer(3,GL_FLOAT,7*sizeof(float),0);
  glColorPointer(4,GL_FLOAT,7*sizeof(float),(const void *)(3*sizeof(float)));
  glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
  glDrawArrays(GL_TRIANGLES,0,(GLsizei)water_count);
  glDisable(GL_BLEND);glUseProgram(0);
 }
 if(ripple && !weather && (season==0 || season==3) && daylight>.35f && fmodf(age,17.f)>=.8f && fmodf(age,17.f)<3.f){
  glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);
  for(int ring=0;ring<3;ring++){
   float phase=(fmodf(age,17.f)-.8f-ring*.18f)/1.8f;
   if(phase<0 || phase>1)continue;
   float r=.12f+phase*.96f;
   glColor4f(.74f,.90f,.87f,.72f*(1.f-phase));glLineWidth(1.5f);glBegin(GL_LINE_LOOP);
   for(int j=0;j<40;j++){float a=j*.1570796f;glVertex3f(ripple[0]+r*cosf(a),ripple[1],ripple[2]+r*sinf(a));}
   glEnd();
  }
  glDepthMask(GL_TRUE);glDisable(GL_BLEND);
 }
 /* Wrap rain through a world-aligned volume around the eye. */
 if(weather==2){
  glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);
  glLineWidth(1.f);glColor4f(.55f,.68f,.76f,.25f+.16f*daylight);glBegin(GL_LINES);
  for(int k=0;k<160;k++){
   float dx=k*7.937f+age*.9f-east,dz=k*k*.231f-north,dy=k*3.831f-age*6.f-eye;
   float px=east+dx-12.f*floorf(dx/12.f)-6.f,pz=north+dz-12.f*floorf(dz/12.f)-6.f;
   float py=eye+dy-9.f*floorf(dy/9.f)-3.f;
   glVertex3f(px,py,pz);glVertex3f(px+.033f,py-.22f,pz);
  }
  glEnd();glDepthMask(GL_TRUE);glDisable(GL_BLEND);
 }
 /* A hatch hangs over the trout pool during clear, mild daylight. */
 if(ripple && !weather && (season==0 || season==3) && daylight>.35f){
  glColor3f(.58f,.55f,.40f);glBegin(GL_TRIANGLES);
  for(int k=0;k<24;k++){
   float t=age*(.85f+.08f*(k%5))+k;
   float px=ripple[0]+1.5f*sinf(t*.64f+k),pz=ripple[2]+cosf(t*.71f+k);
   float py=ripple[1]+.12f+.18f*(1.f+sinf(t*1.6f));
   glVertex3f(px-.013f,py,pz);glVertex3f(px+.015f,py+.023f,pz);glVertex3f(px,py-.012f,pz+.011f);
  }
  glEnd();
 }
 if(marker){
  glColor3f(.94f,.75f,.40f);glLineWidth(2.f);glBegin(GL_LINE_LOOP);
  for(int j=0;j<32;j++){float a=j*.19634954f;glVertex3f(marker[0]+.25f*cosf(a),marker[1],marker[2]+.25f*sinf(a));}
  glEnd();
 }
 if(high)river_bloom(s,x,y,w,h);
 if(photo){
  GLuint samples=0;
  if(photo_query){glGetQueryObjectuiv(photo_query,GL_QUERY_RESULT,&samples);glDeleteQueries(1,&photo_query);}
  if(!samples){photo=NULL;result=1;}
 }
 if(photo){
  glPushClientAttrib(GL_CLIENT_PIXEL_STORE_BIT);glPixelStorei(GL_PACK_ALIGNMENT,1);
  glPixelStorei(GL_PACK_ROW_LENGTH,0);glPixelStorei(GL_PACK_SKIP_PIXELS,0);glPixelStorei(GL_PACK_SKIP_ROWS,0);
  glReadPixels(x,y,w,h,GL_RGB,GL_UNSIGNED_BYTE,photo);glPopClientAttrib();
 }
 /* Screen-space trail markers: three berries and a pointer to the next stop. */
 glLoadIdentity();glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,w,0,h,-1,1);
 glUseProgram(0);glDisable(GL_DEPTH_TEST);
 float radius=(w<h?w:h)*.044f;
 if(lens>0){
  glColor3f(.94f,.92f,.76f);glLineWidth(2.f);
  glBegin(GL_LINES);
  glVertex2f(.5f*w-radius*.37f,.5f*h);glVertex2f(.5f*w+radius*.37f,.5f*h);
  glVertex2f(.5f*w,.5f*h-radius*.37f);glVertex2f(.5f*w,.5f*h+radius*.37f);
  glEnd();
  for(int k=0;k<4;k++){
   float cx=(k%2?.83f:.17f)*w,cy=(k/2?.75f:.25f)*h;
   glBegin(GL_LINE_STRIP);glVertex2f(cx+(k%2?-1:1)*radius,cy);
   glVertex2f(cx,cy);glVertex2f(cx,cy+(k/2?-1:1)*radius);glEnd();
  }
 }
 for(int i=0;i<4&&!lens;i++){
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

static int river_image(void *ptr,int x,int y,int w,int h,int pw,int ph,const void *rgb,int fit){
 struct gpu_scene *s=ptr;
 if(!s||scene_target(s,s->canvas))return -1;
 if(rgb){
  if(pw<1||ph<1||pw>4096||ph>4096)return SDL_SetError("Invalid photo dimensions");
  SDL_Texture *image=SDL_CreateTexture(s->device,SDL_PIXELFORMAT_RGB24,SDL_TEXTUREACCESS_STATIC,pw,ph);
  if(!image)return -1;
  if(SDL_UpdateTexture(image,NULL,rgb,pw*3)){SDL_DestroyTexture(image);return -1;}
  SDL_SetTextureScaleMode(image,SDL_ScaleModeLinear);
  if(s->river_print)SDL_DestroyTexture(s->river_print);
  s->river_print=image;s->print_w=pw;s->print_h=ph;
 }
 if(!s->river_print)return -1;
 float scale=fminf((float)w/s->print_w,(float)h/s->print_h);
 SDL_Rect frame={x,y,w,h},dest={0,0,(int)(s->print_w*scale),(int)(s->print_h*scale)};
 if(!fit)return SDL_RenderCopy(s->device,s->river_print,NULL,&frame);
 dest.x=x+(w-dest.w)/2;dest.y=y+(h-dest.h)/2;
 SDL_SetRenderDrawColor(s->device,23,28,26,255);
 if(SDL_RenderFillRect(s->device,&frame))return -1;
 return SDL_RenderCopy(s->device,s->river_print,NULL,&dest);
}

int pocket_scene_river_photo(void *ptr,int x,int y,int w,int h,int pw,int ph,const void *rgb){
 return river_image(ptr,x,y,w,h,pw,ph,rgb,1);
}
int pocket_scene_river_map(void *ptr,int x,int y,int w,int h,int pw,int ph,const void *rgb){
 return river_image(ptr,x,y,w,h,pw,ph,rgb,0);
}

/* Botanical line drawings in the margin of a plant discovery page. */
int pocket_scene_plant_sketch(void *ptr,int x,int y,int w,int h,int kind){
 struct gpu_scene *s=ptr;
 if(!s||w<1||h<1||scene_target(s,s->canvas))return -1;
 float size=fminf(w,h)*.88f,cx=x+w*.5f,base=y+(h+size)*.5f;
 SDL_Renderer *r=s->device;
 SDL_SetRenderDrawBlendMode(r,SDL_BLENDMODE_BLEND);
 for(int stem=0;stem<(kind==2?1:3);stem++){
  float tilt=(stem-1)*.29f;
  if(kind==2)tilt=0;
  float len=size*(1.f-fabsf(tilt));
  float tip=cx+len*tilt;
  SDL_SetRenderDrawColor(r,58,75,48,230);
  SDL_RenderDrawLineF(r,cx,base,tip,base-len);
  int pairs=kind==2?14:kind==3?17:7;
  for(int j=1;j<pairs;j++){
   float t=(float)j/pairs;
   float ax=cx+len*tilt*t,ay=base-len*t;
   float span=len*(kind==2?.31f*(1.f-t):.19f*sinf(3.14159f*t));
   for(int sign=-1;sign<=1;sign+=2){
    float bx=ax+sign*span,by=ay+span*(kind==2?.37f:-.64f);
    SDL_SetRenderDrawColor(r,57,84,55,225);
    SDL_RenderDrawLineF(r,ax,ay,bx,by);
    if(kind==1){
     for(int k=1;k<=12;k++){
      float u=(k-.5f)/12.f;
      float mid=ay+(by-ay)*u,leaf=span*.22f*sinf(3.14159f*u);
      SDL_RenderDrawLineF(r,ax+(bx-ax)*u,mid-leaf,ax+(bx-ax)*u,mid+leaf);
     }
     if(j%2==0){
      SDL_SetRenderDrawColor(r,54,67,108,245);
      float radius=fmaxf(2.f,len*.025f);
      for(int k=-(int)radius;k<=(int)radius;k++){
       float half=sqrtf(radius*radius-k*k);
       SDL_RenderDrawLineF(r,ax+sign*span*.4f-half,ay+k,ax+sign*span*.4f+half,ay+k);
      }
     }
    }else{
     for(int k=1;k<9;k++){
      float u=k/9.f,px=ax+(bx-ax)*u,py=ay+(by-ay)*u;
      float needle=span*.20f*(1.f-u*.65f);
      SDL_RenderDrawLineF(r,px,py,px+sign*needle,py-needle);
      SDL_RenderDrawLineF(r,px,py,px+sign*needle,py+needle*.48f);
     }
    }
   }
  }
 }
 return 0;
}

/* First-person rod, bowed fly line and floating fly in the walk viewport. */
int pocket_scene_fishing_rod(void *ptr,int x,int y,int w,int h,float u,float v,float bend){
 struct gpu_scene *s=ptr;
 if(!s||scene_target(s,s->canvas))return -1;
 SDL_Renderer *r=s->device;
 SDL_Rect old,clip={x,y,w,h};
 SDL_bool clipped=SDL_RenderIsClipEnabled(r);
 SDL_RenderGetClipRect(r,&old);
 SDL_RenderSetClipRect(r,&clip);
 float bx=x+w*.60f,by=y+h,tx=x+w*.54f,ty=y+h*(.42f+.12f*bend);
 float ax=bx,ay=by;
 for(int i=1;i<=18;i++){
  float t=i/18.f,px=bx+(tx-bx)*t+.08f*w*sinf(t*3.14159f),py=by+(ty-by)*t;
  SDL_SetRenderDrawColor(r,i<5?195:95,i<5?148:84,i<5?86:66,255);
  for(int j=0;j<1+(int)(4*(1-t));j++)SDL_RenderDrawLineF(r,ax+j,ay,px+j,py);
  ax=px;ay=py;
 }
 /* The reel sits just above the cork grip. */
 float rx=bx+.010f*w,ry=by-.07f*h,radius=fminf(w,h)*.015f;
 SDL_SetRenderDrawColor(r,179,163,121,255);
 for(int i=0;i<14;i++){
  float a=i*.448799f,b=a+.448799f;
  SDL_RenderDrawLineF(r,rx+radius*cosf(a),ry+radius*sinf(a),rx+radius*cosf(b),ry+radius*sinf(b));
  if(i%3==0)SDL_RenderDrawLineF(r,rx,ry,rx+radius*cosf(a),ry+radius*sinf(a));
 }
 for(int i=1;i<=18;i++){
  float t=i/18.f,px=tx+(x+w*u-tx)*t,py=ty+(y+h*v-ty)*t+.064f*h*(1-bend)*sinf(t*3.14159f);
  SDL_SetRenderDrawColor(r,223,225,193,225);
  SDL_RenderDrawLineF(r,ax,ay,px,py);ax=px;ay=py;
 }
 SDL_SetRenderDrawColor(r,255,210,94,255);
 SDL_FRect fly={ax-3,ay-2,6,4};SDL_RenderFillRectF(r,&fly);
 SDL_RenderSetClipRect(r,clipped?&old:NULL);
 return 0;
}
