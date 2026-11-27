/* Baked skinning poses share indices, smooth normals and one material atlas. */
static void market_person_release(struct posed_person *model){
 glDeleteBuffers(1,&model->mesh);glDeleteTextures(1,&model->atlas);glDeleteProgram(model->program);
 model->mesh=model->atlas=model->program=0;
}

int pocket_scene_market_person(void *ptr,unsigned slot,const void *data,unsigned bytes){
 struct gpu_scene *s=ptr;
 uint32_t header[6];
 if(!s||slot>=2||!data||bytes<sizeof(header))return SDL_SetError("Incomplete market person");
 struct posed_person *model=&s->people[slot];
 memcpy(header,data,sizeof(header));
 unsigned nv=header[1],ni=header[2],frames=header[3],w=header[4],h=header[5];
 if(memcmp(data,"NPC2",4)||!nv||nv>100000||!ni||ni>500000||frames!=17||w!=2048||h!=2048)
  return SDL_SetError("Invalid market person");
 size_t geometry=4u*ni+12u*nv*(1u+frames);
 if(sizeof(header)+sizeof(model->sole)+geometry+4u*w*h!=bytes)return SDL_SetError("Invalid market mesh length");
 memcpy(model->sole,(const unsigned char *)data+sizeof(header),sizeof(model->sole));
 const unsigned char *mesh=(const unsigned char *)data+sizeof(header)+sizeof(model->sole);
 const uint32_t *indices=(const uint32_t *)mesh;
 for(unsigned i=0;i<ni;i++)if(indices[i]>=nv)return SDL_SetError("Invalid person index");
 if(scene_target(s,s->canvas)||SDL_RenderFlush(s->device))return -1;
 if(model->program)return 0;
 const char *vs="#version 120\n"
  "uniform float blend;varying vec3 uv;varying float light;"
  "void main(){vec3 pos=mix(gl_Vertex.xyz,gl_MultiTexCoord1.xyz,blend)*.0001;"
  "vec3 n=normalize(mix(gl_Normal,gl_MultiTexCoord2.xyz/32767.,blend));"
  "light=.68+.33*max(0.,dot(n,normalize(vec3(-.47,.79,.38))))+.09*n.y;"
  "uv=gl_MultiTexCoord0.xyz;gl_Position=gl_ModelViewProjectionMatrix*vec4(pos,1.);}";
 const char *fs="#version 120\n"
  "uniform vec3 coat;uniform int worker;uniform sampler2D atlas;varying vec3 uv;varying float light;"
  "void main(){vec4 c=texture2D(atlas,uv.xy);if(c.a<.46)discard;"
  "vec3 paint=c.rgb;if(uv.z>.5 && uv.z<2.5)paint*=uv.z<1.5?coat:vec3(.19,.22,.25);"
  "if(worker!=0 && uv.z>2.5)paint=mix(vec3(.075,.08,.07),vec3(.25,.25,.22),c.g);"
  "gl_FragColor=vec4(paint*light,1.);}";

 GLuint vert=wildlife_shader(GL_VERTEX_SHADER,vs);if(!vert)return -1;
 GLuint frag=wildlife_shader(GL_FRAGMENT_SHADER,fs);if(!frag){glDeleteShader(vert);return -1;}
 model->program=glCreateProgram();
 glAttachShader(model->program,vert);glAttachShader(model->program,frag);glLinkProgram(model->program);
 glDeleteShader(vert);glDeleteShader(frag);
 GLint ok;glGetProgramiv(model->program,GL_LINK_STATUS,&ok);
 if(!ok){market_person_release(model);return SDL_SetError("Market person shader failed to link");}
 GLint previous,allocated;
 glGetIntegerv(GL_ARRAY_BUFFER_BINDING,&previous);
 glPushAttrib(GL_TEXTURE_BIT);glPushClientAttrib(GL_CLIENT_PIXEL_STORE_BIT);
 glGenBuffers(1,&model->mesh);glBindBuffer(GL_ARRAY_BUFFER,model->mesh);
 glBufferData(GL_ARRAY_BUFFER,geometry,mesh,GL_STATIC_DRAW);
 glGetBufferParameteriv(GL_ARRAY_BUFFER,GL_BUFFER_SIZE,&allocated);
 glBindBuffer(GL_ARRAY_BUFFER,previous);
 glActiveTexture(GL_TEXTURE0);glGenTextures(1,&model->atlas);glBindTexture(GL_TEXTURE_2D,model->atlas);
 glBindBuffer(GL_PIXEL_UNPACK_BUFFER,0);glPixelStorei(GL_UNPACK_ALIGNMENT,1);glPixelStorei(GL_UNPACK_ROW_LENGTH,0);
 glPixelStorei(GL_UNPACK_SKIP_ROWS,0);glPixelStorei(GL_UNPACK_SKIP_PIXELS,0);
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,mesh+geometry);
 glGenerateMipmap(GL_TEXTURE_2D);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
 GLint tex_w;glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_WIDTH,&tex_w);
 glPopClientAttrib();glPopAttrib();
 if((size_t)allocated!=geometry||tex_w!=(GLint)w){market_person_release(model);return SDL_SetError("Market person upload failed");}
 model->nv=nv;model->ni=ni;
 return 0;
}

static void market_person_draw(struct posed_person *model,int kind,float pose,const float *coat){
 if(!model->program)return;
 /* Frames 0..11 form one stride. 12 is idle, 13..16 are the counter reach. */
 float phase=kind==1?13.f+3.f*pose:pose;
 unsigned a=(unsigned)phase,b=a<12?(a+1)%12:(a>=13 && a<16?a+1:a);
 glPushAttrib(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT|GL_ENABLE_BIT|GL_CURRENT_BIT);
 glDisable(GL_TEXTURE_2D);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);
 for(int side=0;side<2;side++){
  const float *from=model->sole[a][side],*to=model->sole[b][side];
  float weight=phase-a,x=from[0]+weight*(to[0]-from[0]),z=from[2]+weight*(to[2]-from[2]);
  float gap=from[1]+weight*(to[1]-from[1]),opacity=.52f*fmaxf(0.f,1.f-gap/.22f);
  glBegin(GL_TRIANGLE_FAN);glColor4f(.07f,.06f,.05f,opacity);glVertex3f(x,.006f,z);
  glColor4f(.08f,.07f,.06f,0.f);
  for(int j=0;j<=20;j++){float angle=j*.3141593f;
   glVertex3f(x+.105f*cosf(angle),.006f,z+.17f*sinf(angle));}
  glEnd();
 }
 glPopAttrib();
 size_t uv=model->ni*4u,first=uv+model->nv*12u,step=model->nv*12u;
 size_t pa=first+step*a,pb=first+step*b;
 GLint previous,index;
 glGetIntegerv(GL_ARRAY_BUFFER_BINDING,&previous);glGetIntegerv(GL_ELEMENT_ARRAY_BUFFER_BINDING,&index);
 glPushClientAttrib(GL_CLIENT_VERTEX_ARRAY_BIT);glPushAttrib(GL_TEXTURE_BIT);
 glBindBuffer(GL_ARRAY_BUFFER,model->mesh);glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,model->mesh);
 glVertexPointer(3,GL_SHORT,12,(const void *)pa);glEnableClientState(GL_VERTEX_ARRAY);
 glNormalPointer(GL_SHORT,12,(const void *)(pa+6));glEnableClientState(GL_NORMAL_ARRAY);
 glDisableClientState(GL_COLOR_ARRAY);
 glClientActiveTexture(GL_TEXTURE0);glEnableClientState(GL_TEXTURE_COORD_ARRAY);glTexCoordPointer(3,GL_FLOAT,12,(const void *)uv);
 glClientActiveTexture(GL_TEXTURE1);glEnableClientState(GL_TEXTURE_COORD_ARRAY);glTexCoordPointer(3,GL_SHORT,12,(const void *)pb);
 glClientActiveTexture(GL_TEXTURE2);glEnableClientState(GL_TEXTURE_COORD_ARRAY);glTexCoordPointer(3,GL_SHORT,12,(const void *)(pb+6));
 glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,model->atlas);
 glUseProgram(model->program);
 glUniform1f(glGetUniformLocation(model->program,"blend"),phase-a);
 glUniform3fv(glGetUniformLocation(model->program,"coat"),1,coat);
 glUniform1i(glGetUniformLocation(model->program,"worker"),kind==1);
 glDrawElements(GL_TRIANGLES,model->ni,GL_UNSIGNED_INT,0);
 glUseProgram(0);glPopAttrib();glPopClientAttrib();
 glBindBuffer(GL_ARRAY_BUFFER,previous);glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,index);
}
