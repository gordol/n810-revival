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

static void market_people(const float *actors,unsigned count){
 static const float coats[][3]={{.87f,.47f,.12f},{.13f,.44f,.49f},{.49f,.25f,.39f},{.32f,.34f,.49f},{.43f,.42f,.25f}};
 for(unsigned i=0;i<count;i++){
  const float *p=actors+7*i;
  int kind=(int)p[0];
  float pose=p[5];
  glPushMatrix();glTranslatef(p[1],p[2],p[3]);glRotatef(p[4],0,1,0);
  if(kind<=1){
   const float *coat=coats[(unsigned)p[6]%5];
   for(int side=-1;side<=1;side+=2){
    float swing=kind==0?side*pose:0.f;
    glPushMatrix();glTranslatef(side*.105f,.81f,0);glRotatef(24*swing,1,0,0);
    market_body(0,-.35f,0,.09f,.42f,.105f,.16f,.19f,.22f);
    market_body(0,-.73f,.045f,.09f,.075f,.145f,.12f,.12f,.12f);glPopMatrix();
    glPushMatrix();glTranslatef(side*.235f,1.33f,0);glRotatef(kind==0?-21*swing:-36-47*pose,1,0,0);
    market_body(0,-.23f,0,.073f,.27f,.08f,coat[0],coat[1],coat[2]);
    market_body(0,-.49f,.04f,.068f,.09f,.06f,.65f,.46f,.35f);glPopMatrix();
   }
   market_body(0,1.10f,0,.24f,.36f,.15f,coat[0],coat[1],coat[2]);
   if(kind==1)market_body(0,1.01f,.085f,.185f,.36f,.095f,.88f,.46f,.15f);
   market_body(0,1.56f,0,.124f,.172f,.13f,.69f,.51f,.40f);
   market_body(0,1.68f,-.018f,.13f,.085f,.14f,.20f,.17f,.16f);
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
