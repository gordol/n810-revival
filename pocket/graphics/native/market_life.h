/* World-space market actors. Positions are simulated in metres on the CPU. */
static void market_body(float x,float y,float z,float rx,float ry,float rz,float r,float g,float b){
 glPushMatrix();glTranslatef(x,y,z);glScalef(rx,ry,rz);
 river_hiker_band(-1.f,-.55f,.12f,.85f,r,g,b);
 river_hiker_band(-.55f,.35f,.85f,1.f,r,g,b);
 river_hiker_band(.35f,1.f,1.f,.12f,r,g,b);
 glPopMatrix();
}

static void market_panel(float x,float y,float z,float w,float h,float d,float r,float g,float b){
 glBegin(GL_QUADS);
 for(int side=-1;side<=1;side+=2){
  glColor3f(r*.84f,g*.84f,b*.84f);
  glVertex3f(x+side*w,y,z-d);glVertex3f(x+side*w,y+h,z-d);
  glVertex3f(x+side*w,y+h,z+d);glVertex3f(x+side*w,y,z+d);
  glColor3f(r*.94f,g*.94f,b*.94f);
  glVertex3f(x-w,y,z+side*d);glVertex3f(x+w,y,z+side*d);
  glVertex3f(x+w,y+h,z+side*d);glVertex3f(x-w,y+h,z+side*d);
 }
 glColor3f(r,g,b);glVertex3f(x-w,y+h,z-d);glVertex3f(x+w,y+h,z-d);
 glVertex3f(x+w,y+h,z+d);glVertex3f(x-w,y+h,z+d);glEnd();
}

#include "market_person.h"

/* A draped waterproof bib bridges the thighs and wraps the hips. */
static void fishmonger_apron(void){
 static const float cut[][3]={{.56f,.184f,.177f},{.71f,.197f,.170f},{.90f,.211f,.165f},
   {1.04f,.199f,.157f},{1.14f,.161f,.158f},{1.31f,.136f,.158f}};
 for(int j=0;j<5;j++){
  glBegin(GL_QUAD_STRIP);
  for(int i=-12;i<=12;i++){
   float t=(float)i/12.f;
   for(int k=j;k<=j+1;k++){
    float fold=.009f*cosf(t*16.f+.7f*k)*(1.f-.14f*k);
    float light=.85f+.11f*cosf(t*15.f+.7f*k)-.13f*t;
    glColor3f(.84f*light,.40f*light,.13f*light);
    glVertex3f(cut[k][1]*t,cut[k][0]+.01f*t*t,cut[k][2]+fold-.083f*t*t);
   }
  }
  glEnd();
 }
 for(int side=-1;side<=1;side+=2){
  glBegin(GL_QUAD_STRIP);glColor3f(.43f,.27f,.14f);
  for(int k=0;k<=18;k++){
   float a=3.14159265f*k/18.f;
   for(int e=0;e<2;e++)glVertex3f(side*(.105f+.025f*e),1.30f+.17f*sinf(a),.157f*cosf(a)+.012f);
  }
  glEnd();
 }
}

/* Paper-wrapped stems in a cross-body market tote. */
static void market_flowers(void){
 glColor3f(.46f,.32f,.21f);glBegin(GL_QUAD_STRIP);
 for(int j=0;j<=16;j++){
  float a=j*3.14159265f/16.f,x=-.19f+.086f*cosf(a),y=.93f+.13f*sinf(a);
  glVertex3f(x-.009f,y,.15f);glVertex3f(x+.009f,y,.15f);
 }
 glEnd();
 market_body(-.19f,.83f,.14f,.115f,.17f,.08f,.70f,.52f,.33f);
 for(int j=0;j<9;j++){
  float a=j*2.40f,x=-.21f+.075f*cosf(a),z=.16f+.067f*sinf(a),y=1.03f+.035f*cosf(a*3);
  glColor3f(.21f,.36f,.15f);glBegin(GL_LINES);glVertex3f(-.19f,.93f,.15f);glVertex3f(x,y,z);glEnd();
  for(int k=0;k<5;k++){
   float angle=k*1.2566f;
   market_body(x+.019f*cosf(angle),y,z+.019f*sinf(angle),.017f,.012f,.017f,.93f,j%3?.42f:.73f,.54f);
  }
 }
}

/* Cross sections of a beagle from rump through withers, throat, brow and muzzle.
   Catmull-Rom interpolation keeps the neck continuous with the rib cage. */
static void hound_coat(void){
 static const float rings[][4]={{-.35f,.42f,.012f,.03f},{-.30f,.40f,.093f,.12f},
  {-.21f,.38f,.12f,.15f},{-.09f,.39f,.105f,.12f},{.06f,.39f,.129f,.16f},
  {.15f,.42f,.119f,.17f},{.19f,.50f,.091f,.135f},{.220f,.57f,.096f,.108f},
  {.27f,.57f,.090f,.093f},{.31f,.54f,.070f,.056f},{.384f,.54f,.054f,.044f},{.406f,.54f,.038f,.034f}};
 for(int j=0;j<33;j++){
  glBegin(GL_QUAD_STRIP);
  for(int k=0;k<=28;k++){
   float a=k*6.2831853f/28.f,up=cosf(a),side=sinf(a);
   for(int e=0;e<2;e++){
    int n=(j+e)/3;if(n>10)n=10;
    float t=(j+e)/3.f-n,v[4];
    for(int m=0;m<4;m++){
     float p=rings[n?n-1:0][m],q=rings[n][m],r=rings[n+1][m],s=rings[n<10?n+2:11][m];
     v[m]=q+.5f*t*((r-p)+t*((2*p-5*q+4*r-s)+t*(3*q-p-3*r+s)));
    }
    float light=.79f+.16f*up+.10f*side;
    int white=up<-.52f || (v[0]>.30f && (fabsf(side)<.28f || up<.55f));
    int saddle=v[0]<.145f && up>.02f+.23f*sinf(9*v[0]+side);
    glColor3f(light*(white?.94f:saddle?.17f:.76f),light*(white?.89f:saddle?.14f:.45f),
              light*(white?.78f:saddle?.13f:.23f));
    glVertex3f(side*v[2],v[1]+up*v[3],v[0]);
   }
  }
  glEnd();
 }
}

static void plaza_dog(float phase){
 hound_coat();
 market_body(0,.556f,.402f,.043f,.027f,.024f,.105f,.085f,.075f);
 for(int side=-1;side<=1;side+=2){
  market_body(side*.073f,.590f,.307f,.016f,.017f,.016f,.12f,.085f,.05f);
  market_body(side*.078f,.597f,.319f,.004f,.004f,.004f,.93f,.91f,.82f);
  glPushMatrix();glTranslatef(side*.086f,.596f,.221f);
  glRotatef(13.f+6.f*sinf(phase),1,0,0);
  market_body(side*.012f,-.074f,-.015f,.032f,.116f,.069f,.40f,.22f,.12f);glPopMatrix();
  for(int end=-1;end<=1;end+=2){
   float stride=side*end*sinf(phase);
   glPushMatrix();glTranslatef(side*.084f,.36f,end*.193f);
   glRotatef(20.f*stride-(end<0?18.f:0.f),1,0,0);
   market_body(0,-.074f,0,end<0?.067f:.040f,.115f,end<0?.084f:.049f,.68f,.40f,.22f);
   glTranslatef(0,-.156f,0);
   glRotatef((end<0?29.f:0.f)-17.f*fmaxf(0,side*end*cosf(phase)),1,0,0);
   market_body(0,-.078f,0,.029f,.103f,.034f,.89f,.83f,.70f);
   market_body(0,-.168f,.017f,.038f,.026f,.059f,.93f,.88f,.78f);glPopMatrix();
  }
 }
 glPushMatrix();glTranslatef(0,.44f,-.287f);glRotatef(18.f*sinf(phase),0,1,0);
 glRotatef(-52.f,1,0,0);market_body(0,.084f,0,.033f,.12f,.039f,.66f,.39f,.20f);
 glRotatef(18.f,1,0,0);market_body(0,.19f,-.019f,.021f,.070f,.024f,.93f,.90f,.79f);glPopMatrix();
}

/* Rounded crown with a higher hairline at the brow and curls down the nape. */
static void cropped_curls(float grey){
 for(int row=0;row<13;row++){
  glBegin(GL_QUAD_STRIP);
  for(int i=0;i<=48;i++){
   float a=i*6.2831853f/48.f;
   for(int j=row;j<=row+1;j++){
    float t=j/13.f*(1.73f-.48f*cosf(a));
    float curl=sinf(15*a+.6f*j)*sinf(j*1.8f);
    float radius=sinf(t)*(1.f+.043f*curl);
    float light=.72f+.19f*cosf(t)+.11f*curl;
    glColor3f(light*(.18f+.39f*grey),light*(.13f+.41f*grey),light*(.105f+.43f*grey));
    glVertex3f(.123f*radius*sinf(a),-.033f+.125f*cosf(t),.128f*radius*cosf(a));
   }
  }
  glEnd();
 }
}

static void market_people(struct gpu_scene *s,const float *actors,unsigned count){
 static const float coats[][3]={{.87f,.47f,.12f},{.13f,.44f,.49f},{.49f,.25f,.39f},{.32f,.34f,.49f},{.43f,.42f,.25f}};
 float leash_hand[3]={0.f,0.f,0.f};
 for(unsigned i=0;i<count;i++){
  const float *p=actors+9*i;
  int kind=(int)p[0];
  float pose=p[5];
  glPushMatrix();glTranslatef(p[1],p[2],p[3]);
  if(kind<=1){
   GLfloat plane[16]={1,p[7],0,0, 0,1,0,0, 0,p[8],1,0, 0,0,0,1};
   glMultMatrixf(plane);
   glPushAttrib(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT|GL_ENABLE_BIT);
   glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);
   glBegin(GL_TRIANGLE_FAN);glColor4f(.09f,.08f,.07f,.38f);glVertex3f(0,.012f,0);
   glColor4f(.10f,.09f,.08f,0);
   for(int k=0;k<=24;k++){float a=k*.2617994f;glVertex3f(.39f*cosf(a),.012f,.41f*sinf(a));}
   glEnd();glPopAttrib();
  }
  glRotatef(p[4],0,1,0);
  if(kind<=1){
   unsigned identity=(unsigned)p[6],seed=identity&32767u;
   const float *base=coats[(seed>>1)%5];
   float coat[3];
   for(unsigned c=0;c<3;c++)coat[c]=base[c]*(.76f+.031f*((seed>>(4+3*c))&7u));
   float size=kind==1?.96f+.025f*seed:.93f+.020f*((seed>>7)&7u);
   float width=kind==1?1.02f:.94f+.024f*((seed>>10)&7u);
   glScalef(width,size,size);
   float anchors[2][3]={{0}};
   market_person_draw(&s->people[kind==0 && (seed&1)],kind,pose,kind==1?coats[3+seed]:coat,
                      kind==1?0.f:((int)((seed>>2)&15u)-7)*.009f,kind==0?seed:0,anchors);
   if(i+1<count && (int)actors[9*(i+1)]==7){
    float yaw=p[4]*.017453293f,gx=width*anchors[0][0],gz=size*anchors[0][2];
    float dx=gx*cosf(yaw)+gz*sinf(yaw),dz=gz*cosf(yaw)-gx*sinf(yaw);
    leash_hand[0]=p[1]+dx;leash_hand[1]=p[2]+size*anchors[0][1]+p[7]*dx+p[8]*dz;leash_hand[2]=p[3]+dz;
   }
   if(kind==1)fishmonger_apron();
   if(kind==0 && (identity&32768u)){
    glPushMatrix();glTranslatef(anchors[0][0]+.19f,anchors[0][1]-1.06f,anchors[0][2]-.15f);
    market_flowers();glPopMatrix();
   }
   unsigned hair=(seed>>4)&3u;
   if(kind==0 && (hair==1 || hair==2)){
    glPushMatrix();glTranslatef(anchors[1][0]+.044f,anchors[1][1],anchors[1][2]-.041f);
    if(hair==2)cropped_curls(((seed>>11)&3u)/3.f);
    else{
    market_body(0,.025f,0,.113f,.075f,.113f,.23f,.28f,.31f);
    market_body(0,.002f,.115f,.095f,.010f,.080f,.19f,.22f,.24f);}
    glPopMatrix();
   }
  }else if(kind==7){
   if(i && (int)actors[9*(i-1)]==0){
    float yaw=p[4]*.017453293f,dx=leash_hand[0]-p[1],dz=leash_hand[2]-p[3];
    float ex=dx*cosf(yaw)-dz*sinf(yaw),ez=dx*sinf(yaw)+dz*cosf(yaw);
    glColor3f(.25f,.17f,.12f);glBegin(GL_LINE_STRIP);
    for(int j=0;j<=12;j++){
     float t=j/12.f;
     glVertex3f(t*ex,.49f+t*(leash_hand[1]-p[2]-.49f)-.13f*sinf(3.14159f*t),.16f+t*(ez-.16f));
    }
    glEnd();
   }
   plaza_dog(pose);
  }else if(kind==6){
   market_body(0,0,0,.12f,.12f,.44f,.86f,.83f,.72f);
  }else if(kind==5){
   market_panel(0,.36f,0,.91f,.84f,2.15f,.83f,.80f,.69f);
   market_panel(0,1.20f,-.55f,.90f,1.00f,1.57f,.89f,.86f,.74f);
   market_panel(0,1.20f,1.44f,.86f,.68f,.40f,.30f,.41f,.45f);
   market_panel(0,1.88f,1.38f,.91f,.14f,.49f,.83f,.80f,.69f);
   for(int side=-1;side<=1;side+=2){
    for(int end=-1;end<=1;end+=2)
     market_body(side*.90f,.37f,end*1.41f,.13f,.34f,.34f,.14f,.15f,.15f);
    market_panel(side*.68f,.81f,2.15f,.15f,.14f,.014f,.95f,.91f,.69f);
   }
  }else if(kind==2){
   glRotatef(55*pose,1,0,0);
   static const float profile[][3]={{-.42f,.023f,.042f},{-.30f,.055f,.088f},
    {-.11f,.105f,.15f},{.15f,.115f,.16f},{.32f,.080f,.105f},{.46f,.016f,.032f}};
   for(int j=0;j<5;j++){
    glBegin(GL_QUAD_STRIP);
    for(int k=0;k<=12;k++){
     float a=k*.5235988f,up=cosf(a);
     float light=.83f-.26f*up;
     glColor3f(light*.82f,light*.93f,light*.92f);
     for(int end=0;end<2;end++){
      const float *ring=profile[j+end];
      glVertex3f(ring[1]*sinf(a),ring[2]*up,ring[0]);
     }
    }
    glEnd();
   }
   glColor3f(.32f,.39f,.38f);glBegin(GL_TRIANGLES);
   glVertex3f(0,0,-.40f);glVertex3f(0,.17f,-.61f);glVertex3f(0,0,-.55f);
   glVertex3f(0,0,-.40f);glVertex3f(0,0,-.55f);glVertex3f(0,-.14f,-.61f);
   glVertex3f(0,.13f,.08f);glVertex3f(0,.25f,-.12f);glVertex3f(0,.12f,-.18f);
   glEnd();
  }else{
   int gull=kind==3;float scale=gull?1.f:.70f;
   glScalef(scale,scale,scale);
   market_body(0,0,0,.11f,.105f,.29f,gull?.85f:.35f,gull?.86f:.36f,gull?.83f:.39f);
   market_body(0,.095f-(gull?0:.07f*pose),.20f,.078f,.082f,.086f,gull?.91f:.26f,gull?.92f:.34f,gull?.86f:.34f);
   if(gull)for(int side=-1;side<=1;side+=2){
    glPushMatrix();glRotatef(side*31*pose,0,0,1);glBegin(GL_TRIANGLES);
    glColor3f(.73f,.76f,.75f);glVertex3f(0,.08f,.13f);glVertex3f(side*.50f,.15f,.08f);glVertex3f(0,.02f,-.23f);
    glColor3f(.37f,.40f,.42f);glVertex3f(side*.50f,.15f,.08f);glVertex3f(side*.72f,.12f,-.18f);glVertex3f(0,.02f,-.23f);
    glEnd();glPopMatrix();
   }
  }
  glPopMatrix();
 }
}
