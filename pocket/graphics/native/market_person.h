/* Baked skinning poses share indices, smooth normals and one material atlas. */
/* Each choice has its own hash stream. The carried-item bit is stripped by
 * the caller, so buying flowers cannot change a shopper's appearance. */
static unsigned market_choice(unsigned seed,unsigned channel,unsigned count){
 uint32_t x=seed+0x9e3779b9u*channel;
 x^=x>>16;x*=0x7feb352du;x^=x>>15;x*=0x846ca68bu;x^=x>>16;
 return x%count;
}

enum { MARKET_HEAD_LOOKS=9 };
static const float market_dyes[][3]={
 {.12,.14,.17},{.26,.28,.30},{.48,.48,.46},{.84,.80,.71},{.95,.91,.86},
 {.14,.21,.32},{.24,.36,.51},{.41,.59,.69},{.12,.41,.42},{.27,.43,.34},
 {.37,.39,.22},{.61,.53,.37},{.46,.31,.22},{.70,.36,.22},{.75,.56,.22},
 {.57,.20,.21},{.41,.17,.25},{.50,.34,.49},{.72,.47,.53},{.48,.48,.65}
};
static const float market_hair_colors[][3]={
 {.09,.075,.069},{.19,.12,.08},{.35,.22,.15},{.51,.26,.14},
 {.59,.46,.29},{.78,.67,.48},{.48,.46,.43},{.78,.77,.72}
};
/* Art-directed frequencies for the simulated crowd. All eight swatches
 * remain reachable at every complexion, including silver hair. */
static const float *market_hair_swatch(unsigned seed){
 unsigned tone=market_choice(seed,7,16),roll=market_choice(seed,9,100);
 if(roll<9)return market_hair_colors[6+roll%2];
 if(roll<9+(16-tone))return market_hair_colors[5];
 if(roll<32-tone)return market_hair_colors[4];
 if(roll<39-tone)return market_hair_colors[3];
 return market_hair_colors[market_choice(seed,13,3)];
}
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
 if(memcmp(data,"NPC3",4)||!nv||nv>100000||!ni||ni>500000||frames!=16||w!=2048||h!=2048)
  return SDL_SetError("Invalid market person");
 size_t geometry=4u*ni+12u*nv*(1u+frames);
 if(sizeof(header)+sizeof(model->sole)+geometry+4u*w*h!=bytes)return SDL_SetError("Invalid market mesh length");
 memcpy(model->sole,(const unsigned char *)data+sizeof(header),sizeof(model->sole));
 const unsigned char *mesh=(const unsigned char *)data+sizeof(header)+sizeof(model->sole);
 /* Stable grip and crown vertices in the two packaged NPC3 topologies. */
 static const unsigned anchor_vertex[2][2]={{4673,3934},{4257,3160}};
 const int16_t *posed=(const int16_t *)(mesh+4u*ni+12u*nv);
 for(unsigned j=0;j<2;j++){
  unsigned v=anchor_vertex[slot][j];
  if(v>=nv)return SDL_SetError("Missing market person attachment");
  for(unsigned f=0;f<frames;f++)for(unsigned k=0;k<3;k++)
   model->attachments[f][j][k]=posed[6u*(f*nv+v)+k]*.0001f;
 }
 model->skin_tile=slot==0?6u:5u;
 const uint32_t *indices=(const uint32_t *)mesh;
 for(unsigned i=0;i<ni;i++)if(indices[i]>=nv)return SDL_SetError("Invalid person index");
 if(scene_target(s,s->canvas)||SDL_RenderFlush(s->device))return -1;
 if(model->program)return 0;
 const char *vs="#version 120\n"
  "uniform float blend,face,skinTile;uniform int outfit,pantCut;uniform float buildShape;varying vec3 body,uv;varying float light;"
  "void main(){vec3 pos=mix(gl_Vertex.xyz,gl_MultiTexCoord1.xyz,blend)*.0001;"
  "pos.x*=1.+face*smoothstep(1.37,1.54,pos.y);"
  "vec3 n=normalize(mix(gl_Normal,gl_MultiTexCoord2.xyz/32767.,blend));"
  "body=gl_MultiTexCoord3.xyz*.0001;"
  "float waist=(1.-smoothstep(.12,.21,abs(body.x)))*exp(-20.*(body.y-1.08)*(body.y-1.08));"
  "pos.xz*=1.+buildShape*waist;"
  "if(gl_MultiTexCoord0.z>1.5&&gl_MultiTexCoord0.z<2.5){float leg=1.-smoothstep(.49,.78,body.y);"
  "if(pantCut==2||pantCut==4)pos+=n*(.010*leg*smoothstep(.10,.19,body.y));}"
  "if(gl_MultiTexCoord0.z>.5&&gl_MultiTexCoord0.z<1.5){"
  "if(outfit==3||outfit==6)pos+=n*.013;"
  "if(outfit==8||outfit==9)pos+=n*(outfit==8?.012:.018);"
  "if(outfit==10)pos+=n*(.021+.008*cos(body.y*78.));"
  "if(outfit==4)pos+=n*.024*(1.-smoothstep(.15,.22,abs(body.x)));}"
  "float tile=floor(gl_MultiTexCoord0.x*4.)+4.*floor(gl_MultiTexCoord0.y*4.);"
  "if(outfit>=8 && outfit<=10 && tile==skinTile && body.y>.82 && body.y<1.40 && abs(body.x)>.105)pos+=n*.009;"
  "light=.68+.33*max(0.,dot(n,normalize(vec3(-.47,.79,.38))))+.09*n.y;"
  "uv=gl_MultiTexCoord0.xyz;gl_Position=gl_ModelViewProjectionMatrix*vec4(pos,1.);}";
 const char *fs="#version 120\n"
  "uniform vec3 coat,trousers,footwear,hairColor;uniform float complexion,skinTile;uniform int worker,outfit,hair,pantCut,shoeCut;uniform sampler2D atlas;varying vec3 body,uv;varying float light;"
  "void main(){vec4 c=texture2D(atlas,uv.xy);if(c.a<.46)discard;"
  "vec3 paint=c.rgb;if(uv.z>.5 && uv.z<2.5)paint*=uv.z<1.5?coat:trousers;"
  "if(uv.z>.5 && uv.z<1.5 && (outfit==1||outfit==2)){vec2 p=fract(uv.xy*4.);float line=smoothstep(.76,.95,cos(96.*p.y));"
  "if(outfit==2)line=max(line,smoothstep(.79,.95,cos(80.*p.x)));paint=mix(paint,vec3(.78,.74,.60)*c.r,.40*line);}"
  "if(outfit==3 && uv.z>.5 && uv.z<1.5){float yoke=smoothstep(1.26,1.27,body.y);paint*=mix(1.,.56,yoke);"
  "float zip=(1.-smoothstep(.002,.006+fwidth(body.x),abs(body.x)))*smoothstep(.045,.08,body.z);"
  "paint=mix(paint,vec3(.68,.64,.52),zip*.85);}"
  "if(uv.z>.5 && uv.z<1.5 && outfit>=4){float arm=smoothstep(.14,.21,abs(body.x));"
  "if(outfit==4){float quilt=.82+.18*smoothstep(.10,.35,abs(fract(body.y*12.)-.5));"
  "paint=mix(paint*quilt,vec3(.78,.74,.65)*c.r,arm);}"
  "if(outfit==5)paint=mix(paint,c.r*vec3(.92,.83,.63),smoothstep(1.06,1.08,body.y)*(1.-smoothstep(1.16,1.18,body.y)));"
  "if(outfit==6){float bib=smoothstep(1.20,1.23,body.y);paint=mix(paint,c.r*vec3(.13,.18,.23),bib*.8);}"
  "if(outfit==7)paint=mix(paint,c.r*vec3(.19,.27,.31),arm*smoothstep(1.0,1.18,body.y));}"
  // Frame-independent cloth coordinates keep seams attached throughout the gait.
  "if(outfit>=8 && uv.z>.5 && uv.z<1.5){float front=smoothstep(.015,.065,body.z);"
  "float x=abs(body.x),y=body.y;float seam=fwidth(body.x)+.002;"
  "if(outfit==8){float opening=.032+.45*max(y-1.14,0.);float neck=front*(1.-smoothstep(opening-seam,opening+seam,x));"
  "paint=mix(paint,c.rgb*vec3(.95,.86,.70),neck);paint*=1.-front*.24*(1.-smoothstep(.004,.012,abs(x-opening)));}"
  "if(outfit==9){float phase=body.x*320.+1.8*sin(y*74.);float rib=cos(phase)*(1.-smoothstep(.5,2.8,fwidth(phase)));"
  "paint*=.96+.14*rib;paint=mix(paint,c.r*vec3(.78,.72,.60),.78*smoothstep(1.26,1.28,y));}"
  "if(outfit==10){float wave=.5+.5*cos(78.*y+2.5*x);paint*=.74+.31*wave;"
  "paint=mix(paint,vec3(.70,.66,.61),front*(1.-smoothstep(.002,.005+seam,x)));}"
  "if(outfit==11){float bib=(1.-smoothstep(.116,.127,x))*(1.-smoothstep(1.25,1.27,y));"
  "float straps=1.-smoothstep(.013,.022,abs(x-.091));paint=mix(paint,c.r*vec3(.27,.39,.48),max(bib,straps));}}"
  "if(uv.z>1.5 && uv.z<2.5){float y=body.y,x=abs(body.x);"
  "if(pantCut==1)paint=mix(paint,vec3(.66,.66,.63)*c.r,.32*exp(-52.*(y-.49)*(y-.49)));"
  "if(pantCut==2){float pocket=smoothstep(.15,.17,x)*smoothstep(.52,.53,y)*(1.-smoothstep(.69,.70,y));paint*=1.-.32*pocket;}"
  "if(pantCut==3)paint=mix(paint,.68*c.rgb,.76*smoothstep(.17,.187,x));"
  "if(pantCut==4)paint*=.61+.39*smoothstep(.195,.205,y);"
  "if(pantCut==5)paint+=vec3(.13)*exp(-180.*abs(x-.10))*smoothstep(.04,.09,body.z);}"
  "if(worker==0 && uv.z>2.5 && uv.z<3.5){float y=body.y,z=body.z;"
  "float height=skinTile==5.? .19:.09;float h=y/height;"
  "paint=footwear*(.75+.25*smoothstep(0.,1.,h));"
  "if(shoeCut==1)paint=mix(paint,vec3(.84,.82,.75),1.-smoothstep(.14,.22,h));"
  "if(shoeCut==2)paint*=.62+.38*smoothstep(.04,.065,z);"
  "if(shoeCut==3)paint=mix(paint,vec3(.74,.70,.61),.76*(1.-smoothstep(.004,.012,abs(z-.074))));"
  "if(shoeCut==4)paint=mix(paint,.5*footwear+.15,.83*smoothstep(.44,.50,h));"
  "if(shoeCut==5)paint=mix(paint,vec3(.75,.72,.66),.62*smoothstep(.48,.60,h)*smoothstep(.4,.9,cos(190.*z)));}"
  "float tile=floor(uv.x*4.)+4.*floor(uv.y*4.);if(tile==skinTile){"
  "vec3 reference=skinTile==5.?vec3(.80,.62,.49):vec3(.85,.69,.57);"
  "vec3 target=mix(vec3(.98,.81,.71),vec3(.72,.48,.34),min(1.,2.*complexion));"
  "target=mix(target,vec3(.32,.19,.14),max(0.,2.*complexion-1.));"
  "paint=c.rgb*(target/reference);}"
  // Maya's base top leaves her arms bare. Extend the outer garment onto the
  // animated arm surface down to the wrist, keeping hands, face and neck free.
  "if(tile==skinTile && outfit>=8 && outfit<=10 && abs(body.x)>.105 && body.y>.82 && body.y<1.40){"
  "float cuff=smoothstep(.82,.835,body.y);vec3 sleeve=coat*(.78+.15*smoothstep(.855,.871,body.y));"
  "if(outfit==10)sleeve*=.82+.18*cos(78.*body.y);if(outfit==9)sleeve=mix(sleeve,vec3(.78,.72,.60),.78*smoothstep(1.26,1.28,body.y));"
  "paint=mix(paint,sleeve,cuff);}"
  "if(tile==skinTile+2. && hair>=1)discard;if(tile==skinTile+2.)paint=hairColor*(.64+1.5*dot(c.rgb,vec3(.30,.59,.11)));"
  "if(worker!=0 && uv.z>2.5 && uv.z<3.5)paint=mix(vec3(.075,.08,.07),vec3(.25,.25,.22),c.g);"
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

static void market_person_draw(struct posed_person *model,int kind,float pose,const float *coat,float face,unsigned identity,float anchors[2][3]){
 if(!model->program)return;
 /* Strides wrap. The standing keys share planted feet. A throw or
    catch starts from its own resting stance; pose 18 settles from a stride. */
 unsigned a,b;
 float weight;
 if(pose<12.f){
  a=(unsigned)pose;b=(a+1)%12;weight=pose-a;
 }else if(pose<14.f){
  a=12;b=13;weight=pose-12.f;
 }else if(pose<16.f){
  a=12;b=14;weight=pose-14.f;
 }else if(pose<18.f){
  a=13;b=15;weight=pose-16.f;
 }else{
  a=0;b=12;weight=pose-18.f;
 }
 weight=fmaxf(0.f,fminf(1.f,weight));
 if(anchors)for(int j=0;j<2;j++)for(int k=0;k<3;k++){
  float u=model->attachments[a][j][k],v=model->attachments[b][j][k];anchors[j][k]=u+(v-u)*weight;
 }
 glPushAttrib(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT|GL_ENABLE_BIT|GL_CURRENT_BIT);
 glDisable(GL_TEXTURE_2D);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);
 for(int side=0;side<2;side++){
  const float *from=model->sole[a][side],*to=model->sole[b][side];
  float x=from[0]+weight*(to[0]-from[0]),z=from[2]+weight*(to[2]-from[2]);
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
 glClientActiveTexture(GL_TEXTURE3);glEnableClientState(GL_TEXTURE_COORD_ARRAY);glTexCoordPointer(3,GL_SHORT,12,(const void *)(first+12*step));
 glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,model->atlas);
 glUseProgram(model->program);
 glUniform1f(glGetUniformLocation(model->program,"blend"),weight);
 glUniform1i(glGetUniformLocation(model->program,"outfit"),kind==1?0:market_choice(identity,1,12));
 glUniform1f(glGetUniformLocation(model->program,"complexion"),market_choice(identity,7,16)/15.f);
 glUniform1i(glGetUniformLocation(model->program,"hair"),kind==0 && anchors?market_choice(identity,8,MARKET_HEAD_LOOKS):0);
 glUniform1f(glGetUniformLocation(model->program,"skinTile"),(float)model->skin_tile);
 glUniform3fv(glGetUniformLocation(model->program,"hairColor"),1,market_hair_swatch(identity));
 glUniform1f(glGetUniformLocation(model->program,"buildShape"),((int)market_choice(identity,10,9)-4)*.05f);
 glUniform1f(glGetUniformLocation(model->program,"face"),face);
 glUniform1i(glGetUniformLocation(model->program,"pantCut"),market_choice(identity,3,6));
 glUniform1i(glGetUniformLocation(model->program,"shoeCut"),market_choice(identity,5,6));
 glUniform3fv(glGetUniformLocation(model->program,"trousers"),1,market_dyes[market_choice(identity,4,20)]);
 glUniform3fv(glGetUniformLocation(model->program,"footwear"),1,market_dyes[market_choice(identity,6,20)]);
 glUniform3fv(glGetUniformLocation(model->program,"coat"),1,coat);
 glUniform1i(glGetUniformLocation(model->program,"worker"),kind==1);
 glDrawElements(GL_TRIANGLES,model->ni,GL_UNSIGNED_INT,0);
 glUseProgram(0);glPopAttrib();glPopClientAttrib();
 glBindBuffer(GL_ARRAY_BUFFER,previous);glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,index);
}
