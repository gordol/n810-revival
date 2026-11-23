/* Draw animated wildlife triangles directly into the SDL compositor canvas. */
struct wildlife_face {float depth;unsigned index;};
static int wildlife_order(const void *a,const void *b){
 const struct wildlife_face *p=a,*q=b;
 return p->depth<q->depth?1:p->depth>q->depth?-1:(p->index>q->index)-(p->index<q->index);
}
int pocket_scene_wildlife(void *ptr,int x,int y,int w,int h,const float *a,const float *b,unsigned nv,
                          const unsigned *faces,unsigned nf,float blend,float yaw,float tilt,float scale,float bob,int appearance,unsigned pose_key){
 const int flight=appearance==1;
 struct gpu_scene *s=ptr;
 if(!s||!a||!b||!faces||w<=0||h<=0||!nv||nv>100000||!nf||nf>100000)return -1;
 SDL_RendererInfo info;
 if(SDL_GetRendererInfo(s->device,&info))return -1;
 if(!strcmp(info.name,"opengl")){
  if(scene_target(s,s->canvas)||SDL_RenderFlush(s->device))return -1;
  return wildlife_gl_draw(&s->wildlife,x,y,w,h,s->width,s->height,a,b,nv,faces,nf,
                          blend,yaw,tilt,scale,bob,appearance,pose_key);
 }
 if(scene_capacity(s,(size_t)nf*3+6+96))return -1;
 float (*p)[4]=malloc(nv*sizeof(*p));
 struct wildlife_face *order=malloc(nf*sizeof(*order));
 if(!p||!order){free(p);free(order);return -1;}
 float cy=cosf(yaw),sy=sinf(yaw),ct=cosf(tilt),st=sinf(tilt);
 for(unsigned i=0;i<nv;i++){
  float v[3];for(int k=0;k<3;k++)v[k]=a[4*i+k]+blend*(b[4*i+k]-a[4*i+k]);
  float z=v[0]*sy+v[2]*cy,up=v[1]+bob-(flight?0.f:.18f);
  p[i][0]=x+.5f*w+(v[0]*cy-v[2]*sy)*scale;
  p[i][1]=y+.5f*h-(up*ct+z*st)*scale;
  p[i][2]=(z*ct-up*st)*scale;
  p[i][3]=a[4*i+3]+blend*(b[4*i+3]-a[4*i+3]);
 }
 for(unsigned i=0;i<nf;i++){
  const unsigned *f=faces+4*i;
  if(f[0]>=nv||f[1]>=nv||f[2]>=nv){free(p);free(order);return -1;}
  order[i]=(struct wildlife_face){p[f[0]][2]+p[f[1]][2]+p[f[2]][2],i};
 }
 qsort(order,nf,sizeof(*order),wildlife_order);
 Scene_Vertex *v=s->vertices;
 scene_quad(v,x,y,w,h,scene_rgb(flight?0x507d9c:0x758f82),0,0,0,0);
 for(unsigned k=0;k<6;k++)if(v[k].position.y>y)v[k].color=scene_rgb(flight?0xcbdce1:0xb4ad88);
 unsigned count=6;
 if(!flight){
  float cx=x+.5f*w-.055f*scale,cy0=y+.5f*h+.18f*ct*scale;
  for(unsigned i=0;i<32;i++){
   v[count++]=(Scene_Vertex){{cx,cy0},scene_rgb(0x6f7056),{0,0}};
   for(unsigned j=i;j<=i+1;j++){
    float phase=j*.19634954f;
    float px=cx+cosf(phase)*.45f*scale,py=cy0+sinf(phase)*.034f*scale;
    float t=fmaxf(0,fminf(1,(py-y)/h));
    Scene_Color edge={(unsigned char)(117+63*t),(unsigned char)(143+30*t),(unsigned char)(130+6*t),255};
    v[count++]=(Scene_Vertex){{px,py},edge,{0,0}};
   }
  }
 }
 for(unsigned i=0;i<nf;i++){
  const unsigned *f=faces+4*order[i].index;
  for(unsigned k=0;k<3;k++){
   const float *vertex=p[f[k]];
   Scene_Color color=scene_rgb(f[3]);color.r*=vertex[3];color.g*=vertex[3];color.b*=vertex[3];
   v[count++]=(Scene_Vertex){{vertex[0],vertex[1]},color,{0,0}};
  }
 }
 free(p);free(order);
 Scene_Rect clip={x,y,w,h};
 if(scene_target(s,s->canvas)||Scene_RenderSetClipRect(s->device,&clip))return -1;
 int result=Scene_RenderGeometry(s->device,NULL,v,(int)count,NULL,0);
 return Scene_RenderSetClipRect(s->device,NULL)?-1:result;
}
