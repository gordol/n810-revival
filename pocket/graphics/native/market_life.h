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
 for(int j=0;j<=20;j++){
  float a=j*.15708f,x=-.18f*cosf(a),y=.86f+.60f*sinf(a),z=j<10?.155f:-.15f;
  glVertex3f(x-.018f,y,z);glVertex3f(x+.018f,y,z);
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

static void plaza_dog(float phase,float owner_height){
 glColor3f(.23f,.18f,.15f);glBegin(GL_LINE_STRIP);
 for(int j=0;j<=10;j++){
  float t=j*.1f;
  glVertex3f(-.58f*t,.46f+(.42f+owner_height)*t-.15f*sinf(t*3.14159f),.17f-.47f*t);
 }
 glEnd();
 market_body(0,.38f,0,.122f,.15f,.25f,.53f,.31f,.15f);
 market_body(0,.51f,.20f,.107f,.13f,.13f,.62f,.39f,.21f);
 market_body(0,.48f,.31f,.063f,.052f,.09f,.61f,.41f,.25f);
 market_body(0,.49f,.39f,.036f,.026f,.023f,.12f,.10f,.08f);
 for(int side=-1;side<=1;side+=2){
  market_body(side*.094f,.52f,.18f,.031f,.092f,.06f,.36f,.21f,.12f);
  market_body(side*.071f,.55f,.286f,.013f,.014f,.012f,.08f,.07f,.05f);
  for(int end=-1;end<=1;end+=2){
   glPushMatrix();glTranslatef(side*.078f,.31f,end*.139f);
   glRotatef(22.f*end*side*sinf(phase),1,0,0);
   market_body(0,-.124f,0,.036f,.14f,.048f,.49f,.30f,.18f);
   market_body(0,-.268f,.021f,.036f,.031f,.052f,.39f,.25f,.17f);glPopMatrix();
  }
 }
 glPushMatrix();glTranslatef(0,.44f,-.20f);glRotatef(18.f*sinf(phase),0,1,0);
 glRotatef(-42.f,1,0,0);market_body(0,.09f,0,.034f,.14f,.042f,.54f,.34f,.18f);glPopMatrix();
}

static void market_people(struct gpu_scene *s,const float *actors,unsigned count){
 static const float coats[][3]={{.87f,.47f,.12f},{.13f,.44f,.49f},{.49f,.25f,.39f},{.32f,.34f,.49f},{.43f,.42f,.25f}};
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
   market_person_draw(&s->people[kind==0 && (seed&1)],kind,pose,kind==1?coats[3+seed]:coat,
                      kind==1?0.f:((int)((seed>>2)&15u)-7)*.009f);
   if(kind==1)fishmonger_apron();
   if(kind==0 && (identity&32768u))market_flowers();
  }else if(kind==7){
   plaza_dog(pose,p[6]);
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
