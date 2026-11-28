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

/* Cross sections run from tail to nose. Each has a sill, a shoulder and
 * an inset roof or hood, so the glazing follows the rake of the pillars. */
static void street_vehicle(int van,unsigned paint,int lamps){
 static const float coupe[][5]={
  {-2.18f,.78f,.76f,.82f,.70f},{-1.74f,.94f,.85f,.92f,.78f},
  {-1.26f,.98f,.87f,.97f,.78f},{-.70f,.96f,.89f,1.33f,.62f},
  {.14f,.94f,.89f,1.35f,.64f},{.93f,.93f,.80f,.88f,.79f},
  {1.66f,.91f,.73f,.79f,.76f},{2.18f,.74f,.56f,.63f,.65f}};
 static const float delivery[][5]={
  {-2.20f,.87f,1.16f,1.99f,.81f},{-1.96f,.94f,1.19f,2.08f,.85f},
  {-1.30f,.94f,1.19f,2.08f,.85f},{-.58f,.94f,1.19f,2.08f,.85f},
  {.46f,.93f,1.17f,2.02f,.82f},{1.18f,.90f,1.10f,1.26f,.80f},
  {1.75f,.88f,.99f,1.05f,.80f},{2.14f,.84f,.86f,.92f,.77f}};
 static const float colors[][3]={{.73f,.12f,.055f},{.23f,.36f,.45f},{.74f,.71f,.62f},{.16f,.22f,.26f},{.43f,.17f,.18f}};
 const float (*profile)[5]=van?delivery:coupe;
 const float *body=colors[van && !paint?2:paint%5];
 for(int i=0;i<7;i++)for(int side=-1;side<=1;side+=2){
  glBegin(GL_QUAD_STRIP);
  for(int edge=0;edge<4;edge++)for(int end=0;end<2;end++){
   const float *p=profile[i+end];
   float w=edge==0?p[1]*.90f:edge==1?p[1]:edge==2?p[4]:0.f;
   float y=edge==0?.33f:edge==1?p[2]:p[3];
   float light=edge==0?.45f:edge==1?.84f:1.f;
   int glass=(edge>=2 && (i==4 || (!van && i==2))) || (edge==1 && i==3);
   float sheen=edge==2?.20f:edge==3?.08f:0.f;
   if(glass)glColor3f(.08f+sheen,.14f+sheen,.20f+sheen);
   else glColor3f(light*body[0]+sheen*.45f,light*body[1]+sheen*.60f,light*body[2]+sheen*.70f);
   glVertex3f(side*w,y,p[0]);
  }
  glEnd();
 }
 for(int side=-1;side<=1;side+=2){
  const float *end=profile[side<0?0:7];
  glColor3f(body[0]*.85f,body[1]*.85f,body[2]*.85f);
  glBegin(GL_QUADS);
  glVertex3f(-end[1],end[2],end[0]);glVertex3f(end[1],end[2],end[0]);
  glVertex3f(end[4],end[3],end[0]);glVertex3f(-end[4],end[3],end[0]);
  glEnd();
  if(van && side<0)for(int k=-1;k<=1;k+=2)
   market_panel(k*.42f,1.32f,end[0]-.02f,.33f,.48f,.015f,.11f,.17f,.20f);
  market_panel(0,.32f,end[0],end[1]*.98f,end[2]-.32f,.018f,body[0],body[1],body[2]);
  market_panel(0,.38f,end[0]+side*.03f,.48f,.11f,.015f,.10f,.11f,.12f);
  if(side<0){
   market_panel(0,.51f,end[0]-.027f,.17f,.09f,.012f,.83f,.85f,.80f);
   if(!van)market_panel(0,.805f,end[0]+.05f,.76f,.035f,.075f,.14f,.14f,.15f);
  }
  for(int k=-1;k<=1;k+=2){
   float strength=side<0?(lamps&1?1.f:.52f):(lamps&2?1.f:.62f);
   int signal=lamps&(k<0?4:8);
   market_panel(k*end[1]*.72f,end[2]-.14f,end[0]+side*.04f,.17f,.085f,.02f,signal?1.f:strength,signal?.58f:strength*(side<0?.055f:.96f),signal?.01f:strength*(side<0?.025f:.85f));
   float z=k*1.37f;
   glBegin(GL_QUAD_STRIP);
   for(int j=0;j<=24;j++){
    float a=j*.2617994f,y=.36f+.34f*cosf(a),wz=z+.34f*sinf(a);
    glColor3f(.065f,.07f,.074f);glVertex3f(side*.79f,y,wz);glVertex3f(side*.99f,y,wz);
   }
   glEnd();
   for(int ring=0;ring<2;ring++){
    float radius=ring?.215f:.34f;
    glBegin(GL_TRIANGLE_FAN);glColor3f(.12f,.13f,.14f);
    glVertex3f(side*(.992f+.002f*ring),.36f,z);
    for(int j=0;j<=24;j++){
     float shade=ring?(j%3==0?.32f:.68f):.095f;
     glColor3f(shade,shade,shade);glVertex3f(side*(.992f+.002f*ring),.36f+radius*cosf(j*.2617994f),z+radius*sinf(j*.2617994f));
    }
    glEnd();
   }
  }
 }
}
static void trail_bike(void){
 for(int wheel=-1;wheel<=1;wheel+=2){
  glColor3f(.085f,.09f,.10f);glBegin(GL_QUAD_STRIP);
  for(int j=0;j<=32;j++){
   float a=j*.19635f;
   glVertex3f(0,.36f+.35f*cosf(a),wheel*.57f+.35f*sinf(a));
   glVertex3f(0,.36f+.30f*cosf(a),wheel*.57f+.30f*sinf(a));
  }
  glEnd();
  glColor3f(.53f,.56f,.57f);glBegin(GL_LINES);
  for(int j=0;j<12;j++){
   float a=j*.523599f;glVertex3f(0,.36f,wheel*.57f);
   glVertex3f(0,.36f+.31f*cosf(a),wheel*.57f+.31f*sinf(a));
  }
  glEnd();
 }
 glColor3f(.14f,.43f,.58f);glLineWidth(3);glBegin(GL_LINE_STRIP);
 glVertex3f(0,.36f,-.57f);glVertex3f(0,.84f,-.19f);glVertex3f(0,.8f,.38f);
 glVertex3f(0,.38f,0);glVertex3f(0,.36f,-.57f);glEnd();
 glBegin(GL_LINES);glVertex3f(0,.38f,0);glVertex3f(0,.9f,-.22f);
 glVertex3f(0,.36f,.57f);glVertex3f(0,1.01f,.33f);
 glVertex3f(-.32f,1.01f,.33f);glVertex3f(.32f,1.01f,.33f);glEnd();glLineWidth(1);
 market_body(0,.91f,-.23f,.085f,.035f,.13f,.09f,.09f,.10f);
}

static void heavy_vehicle(int kind,int lamps){
 int bus=kind==11;
 if(bus){
  market_panel(0,.44f,0,1.24f,2.62f,5.8f,.22f,.43f,.57f);
  market_panel(0,1.48f,5.81f,1.10f,1.36f,.02f,.13f,.23f,.28f);
  for(int side=-1;side<=1;side+=2)for(int n=0;n<8;n++)
   market_panel(side*1.25f,1.62f,-4.93f+n*1.37f,.015f,1.1f,.61f,.15f,.24f,.27f);
  market_panel(0,3.07f,-2.f,.75f,.22f,1.5f,.65f,.66f,.62f);
 }else{
  market_panel(0,.60f,5.7f,1.22f,2.76f,1.75f,.53f,.22f,.15f);
  market_panel(0,1.79f,7.46f,1.03f,1.04f,.03f,.13f,.20f,.23f);
  market_panel(0,1.04f,-2.12f,1.28f,3.03f,5.68f,.74f,.75f,.72f);
  for(int n=0;n<21;n++)for(int side=-1;side<=1;side+=2)
   market_panel(side*1.29f,1.20f,-7.65f+n*.54f,.018f,2.66f,.028f,.59f,.60f,.58f);
 }
 for(int side=-1;side<=1;side+=2){
  for(int n=0;n<(bus?2:4);n++){
   float axle=bus?(n?3.7f:-3.4f):(float[]){6.2f,2.95f,-5.5f,-6.8f}[n];
   market_body(side*1.17f,.52f,axle,.24f,.54f,.54f,.09f,.10f,.10f);
   market_body(side*1.36f,.52f,axle,.065f,.29f,.29f,.43f,.45f,.44f);
  }
  market_panel(side*.93f,.79f,bus?5.84f:7.49f,.19f,.14f,.025f,1.f,.94f,.78f);
  market_panel(side*.94f,.98f,bus?-5.84f:-7.83f,.17f,.14f,.025f,lamps&1?1.f:.6f,.035f,.025f);
 }
}

static void detailed_vehicle(struct gpu_scene *s,unsigned slot,unsigned paint,int lamps){
 static const GLfloat colors[][3]={{.68f,.022f,.032f},{.14f,.27f,.41f},{.74f,.69f,.57f},
                                    {.12f,.15f,.18f},{.37f,.035f,.072f}};
 const GLfloat sun[]={-.45f,.85f,.35f,0}, ambient[]={.41f,.44f,.48f,1};
 const GLfloat sky[]={.92f,.88f,.82f,1}, shine[]={.76f,.79f,.84f,1}, dull[]={.06f,.06f,.06f,1};
 glPushAttrib(GL_ENABLE_BIT|GL_LIGHTING_BIT|GL_CURRENT_BIT);
 glPushClientAttrib(GL_CLIENT_VERTEX_ARRAY_BIT);
 glEnable(GL_LIGHTING);glEnable(GL_LIGHT0);glEnable(GL_NORMALIZE);glDisable(GL_CULL_FACE);
 glEnable(GL_COLOR_MATERIAL);glColorMaterial(GL_FRONT_AND_BACK,GL_AMBIENT_AND_DIFFUSE);
 glLightModelfv(GL_LIGHT_MODEL_AMBIENT,ambient);glLightfv(GL_LIGHT0,GL_POSITION,sun);
 glLightfv(GL_LIGHT0,GL_DIFFUSE,sky);glLightfv(GL_LIGHT0,GL_SPECULAR,sky);
 glBindBuffer(GL_ARRAY_BUFFER,s->vehicle_mesh[slot]);
 glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_NORMAL_ARRAY);glDisableClientState(GL_COLOR_ARRAY);
 glVertexPointer(3,GL_FLOAT,24,0);glNormalPointer(GL_FLOAT,24,(void *)12);
 unsigned first=0;
 for(unsigned m=0;m<29;m++){
  unsigned n=s->vehicle_groups[slot][m];if(!n)continue;
  int glossy=m==1||m==10||m==11||m==15||m==21;
  glMaterialfv(GL_FRONT_AND_BACK,GL_SPECULAR,glossy?shine:dull);
  glMaterialf(GL_FRONT_AND_BACK,GL_SHININESS,glossy?46.f:8.f);
  if(m==10||m==11)glColor3fv(colors[paint%5]);
  else if(m==1)glColor3f(.095f,.17f,.23f);
  else if(m==13)glColor3f(lamps&1?1.f:.65f,.025f,.025f);
  else if(m==12)glColor3f(.58f,.24f,.04f);
  else if(m==14)glColor3f(lamps&2?1.f:.69f,lamps&2?.97f:.75f,.78f);
  else if(m==15||m==21||m==17||m==9)glColor3f(.62f,.66f,.68f);
  else glColor3f(.065f,.07f,.076f);
  glDrawArrays(GL_TRIANGLES,first,n);first+=n;
 }
 glPopClientAttrib();glPopAttrib();
}

/* Double-ended Sound ferry. The open vehicle deck runs between the two ramps. */
static void docked_ferry(void){
 for(int k=0;k<48;k++){
  float a=k*.130899694f,b=(k+1)*.130899694f;
  glBegin(GL_QUAD_STRIP);
  for(int tier=0;tier<3;tier++){
   float width=tier==0?7.4f:10.f,length=tier==0?41.f:47.f,y=tier==0?-2.f:tier==1?.9f:2.3f;
   glColor3f(.12f+.04f*tier,.21f+.06f*tier,.21f+.04f*tier);
   glVertex3f(width*sinf(a),y,length*cosf(a));glVertex3f(width*sinf(b),y,length*cosf(b));
  }
  glEnd();
 }
 glBegin(GL_TRIANGLE_FAN);glColor3f(.42f,.43f,.41f);glVertex3f(0,2.3f,0);
 for(int k=0;k<=48;k++)glVertex3f(10.f*sinf(k*.130899694f),2.3f,47.f*cosf(k*.130899694f));
 glEnd();
 for(int side=-1;side<=1;side+=2){
  for(int j=-3;j<=3;j++)market_panel(side*7.6f,2.3f,j*7.f,.23f,3.6f,.27f,.86f,.87f,.81f);
  market_panel(0,9.4f,side*17.f,4.1f,2.1f,4.8f,.90f,.90f,.84f);
  market_panel(0,10.2f,side*21.83f,3.7f,.85f,.04f,.18f,.31f,.34f);
 }
 market_panel(0,5.9f,0,8.5f,.5f,31.f,.15f,.31f,.26f);
 market_panel(0,6.4f,0,7.7f,2.7f,27.f,.91f,.90f,.83f);
 for(int side=-1;side<=1;side+=2)
  for(int i=-8;i<=8;i++)market_panel(side*7.72f,7.25f,i*3.f,.04f,1.15f,1.17f,.20f,.32f,.34f);
 market_panel(0,9.1f,0,8.f,.30f,28.f,.22f,.37f,.30f);
 market_panel(0,9.4f,0,1.7f,3.2f,2.4f,.19f,.34f,.27f);
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

/* Head-local coordinates are measured from the posed scalp vertex, +Z forward. */
static void market_headwear(unsigned style,const float *color){
 const float tau=6.2831853f;
 int cap=style==1,loose=style==4;
 for(int row=0;row<12;row++){
  glBegin(GL_QUAD_STRIP);
  for(int i=0;i<=48;i++){
   float a=tau*i/48.f,front=cosf(a),side=sinf(a);
   for(int j=row;j<=row+1;j++){
    float u=j/12.f;
    float edge=cap?1.56f-.09f*front:1.86f-.69f*front+.07f*sinf(3*a);
    float t=u*edge;
    float flow=18.f*a+2.f*u+1.6f*sinf(3.f*a+3.f*u);
    float strand=cosf(flow),ripple=style==2?.037f:.016f;
    float r=sinf(t)*(1.f+(cap?0:ripple*strand)*u);
    float drape=fminf(1.f,fmaxf(0.f,(.73f-front)*1.6f));
    float fall=loose?(.29f-.045f*front+.018f*cosf(5*a))*drape*u*u*u:0;
    if(loose)r+=.09f*drape*u*u*sinf(8*u+2*a);
    float light=.77f+.16f*cosf(t)+.13f*side+.07f*front;
    if(cap)light*=1.f-.17f*powf(fmaxf(0,cosf(6*a)),12.f);
    else light+=.13f*strand*u+.09f*cosf(2*flow+.6f)*u;
    glColor3f(color[0]*light,color[1]*light,color[2]*light);
    glVertex3f((cap?.097f:.092f)*r*side*(1.f+fall),
               -.089f+(cap?.110f:style==5?.095f:.106f)*cosf(t)-fall,
               -.012f+.119f*r*front-fall*.31f);
   }
  }
  glEnd();
 }
 if(cap){
  /* A crescent visor joins the forehead band and dips at the temples. */
  glBegin(GL_QUAD_STRIP);
  for(int i=-12;i<=12;i++){
   float a=i*.095f,c=cosf(a),x=.097f*sinf(a),y=-.083f-.013f*(1-c);
   glColor3f(color[0]*.76f,color[1]*.76f,color[2]*.76f);
   glVertex3f(x,y,.116f*c-.012f);
   glVertex3f(x*1.12f,y-.009f,.116f*c-.012f+.068f*(c-.415f));
  }
  glEnd();
 }
}

/* Continuous swept locks, with three interleaved ridges for plaited hair. */
static void market_tied_hair(unsigned style,const float *color,float gait){
 int bun=style==3,braid=style==6||style==8,twin=style>=7;
 for(int lock=0;lock<(twin?2:1);lock++){
  float side=twin?(lock?1.f:-1.f):0.f;
  for(int row=0;row<24;row++){
   glBegin(GL_QUAD_STRIP);
   for(int i=0;i<=18;i++){
    float a=i*6.2831853f/18.f;
    for(int j=row;j<=row+1;j++){
     float u=j/24.f,twist=3*a+u*32.f;
     float r=bun?.063f*sqrtf(fmaxf(0,1-(2*u-1)*(2*u-1))):
             (.034f-.028f*u)*(1.f+(braid?.21f*cosf(twist):.05f*cosf(6*a+3*u)));
     float y=bun?-.012f-.104f*u:-.09f-(twin?.28f:.34f)*u;
     float z=bun?-.116f:-.111f-.066f*u+.013f*gait*u*u;
     float x=side*(.073f+.044f*sinf(2.2f*u))+.011f*gait*u*u;
     float light=.8f+.16f*sinf(a)+.15f*cosf(bun?6*a+u*31:braid?twist:7*a+u*4);
     if(!bun && j==21)light*=.38f;
     glColor3f(color[0]*light,color[1]*light,color[2]*light);
     glVertex3f(x+r*sinf(a),y,z+r*cosf(a));
    }
   }
   glEnd();
  }
 }
}

static void market_people(struct gpu_scene *s,const float *actors,unsigned count){
 static const float coats[][3]={{.87f,.47f,.12f},{.13f,.44f,.49f},{.49f,.25f,.39f},{.32f,.34f,.49f},{.43f,.42f,.25f},{.87f,.77f,.57f},{.63f,.16f,.18f},{.26f,.39f,.63f},{.76f,.64f,.71f}};
 float leash_hand[3]={0.f,0.f,0.f};
 for(unsigned i=0;i<count;i++){
  const float *p=actors+9*i;
  int kind=(int)p[0];
  float pose=p[5];
  glPushMatrix();glTranslatef(p[1],p[2],p[3]);
  if(kind<=1){
   glPushAttrib(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT|GL_ENABLE_BIT);
   glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);
   glBegin(GL_TRIANGLE_FAN);glColor4f(.09f,.08f,.07f,.38f);glVertex3f(0,.012f,0);
   glColor4f(.10f,.09f,.08f,0);
   for(int k=0;k<=24;k++){float a=k*.2617994f;glVertex3f(.39f*cosf(a),.012f,.41f*sinf(a));}
   glEnd();glPopAttrib();
  }
  glRotatef(p[4],0,1,0);
  if(kind==5 || kind==9 || (kind>=10 && kind<=12) || kind==14 || kind==15){
   /* Rotate a rigid chassis on its longitudinal grade. */
   float yaw=p[4]*.017453293f;
   float grade=fminf(.28f,fmaxf(-.28f,p[7]*sinf(yaw)+p[8]*cosf(yaw)));
   glRotatef(-atanf(grade)*57.29578f,1,0,0);
   glPushAttrib(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT|GL_ENABLE_BIT);
   glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);
   glBegin(GL_TRIANGLE_FAN);glColor4f(.025f,.026f,.032f,.65f);glVertex3f(0,.025f,0);
   glColor4f(.04f,.04f,.045f,0);
   for(int j=0;j<=28;j++){float a=j*.2243995f;glVertex3f(1.38f*cosf(a),.025f,2.7f*sinf(a));}
   glEnd();glPopAttrib();
  }
  if(kind<=1){
   unsigned identity=(unsigned)p[6],seed=identity&32767u;
   const float *coat=market_dyes[market_choice(seed,2,20)];
   float size=kind==1?.96f+.025f*seed:.87f+.016f*((seed>>7)&15u);
   float width=kind==1?1.02f:.89f+.028f*market_choice(seed,11,9);
   glScalef(width,size,size);
   if(kind==0 && pose>=20.f){
    float lift=sinf((pose-20.f)*.5235988f);
    glTranslatef(0,.085f*lift*lift,0);
    glRotatef(8.f,1,0,0);
   }
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
   unsigned hair=market_choice(seed,8,MARKET_HEAD_LOOKS);
   if(kind==0 && hair && s->people[seed&1].program){
    static const unsigned cap_dyes[]={0,1,5,6,8,9,15,16};
    const float *locks=market_hair_swatch(seed);
    float face=((int)((seed>>2)&15u)-7)*.009f;
    glPushMatrix();glScalef(1.f+face,1,1);
    glTranslatef(anchors[1][0],anchors[1][1],anchors[1][2]);
    market_headwear(hair,hair==1?market_dyes[cap_dyes[market_choice(seed,12,8)]]:locks);
    if(hair==3||hair>=6)
     market_tied_hair(hair,locks,pose<12.f?sinf(pose*.5235988f):0.f);
    glPopMatrix();
   }
  }else if(kind==5 || kind==10 || kind==11 || kind==12 || kind==14 || kind==15){
   glPushMatrix();
   if((int)pose&16){
    glRotatef(4.f,0,0,1);
    glScalef(1.02f,.94f,.91f);
   }
   unsigned slot=kind==5?1:kind==11?2:kind==12?3:kind==14?4:kind==15?5:0;
   unsigned paint=(unsigned)p[6];
   if(paint<32 && s->vehicle_mesh[slot])detailed_vehicle(s,slot,paint,(int)pose);
   else if(kind==11 || kind==12)heavy_vehicle(kind,(int)pose);
   else street_vehicle(kind==5,paint%32,(int)pose);
   if((int)pose&16 && kind<11){
    glTranslatef(.07f,.70f,1.6f);glRotatef(-17.f,1,0,0);
    market_panel(0,0,0,.80f,.06f,.48f,.25f,.23f,.22f);
   }
   glPopMatrix();
  }else if(kind==16){
   market_panel(0,1.8f,0,.08f,1.8f,.08f,.38f,.40f,.39f);
   for(int face=0;face<4;face++){
    glRotatef(90.f,0,1,0);
    int red=(face%2)==(pose>.5f);
    market_panel(0,3.35f,.12f,.18f,.45f,.09f,.14f,.15f,.15f);
    market_panel(0,3.61f,.23f,.105f,.11f,.02f,red?.96f:.18f,.055f,.04f);
    market_panel(0,3.10f,.23f,.105f,.11f,.02f,.04f,red?.16f:.92f,.09f);
   }
  }else if(kind==13){
   trail_bike();
  }else if(kind==9 && s->vehicle_mesh[6]){
   detailed_vehicle(s,6,3,2);
   market_panel(-.29f,1.60f,-.12f,.26f,.055f,.11f,pose>=0 && pose<.5f?1.f:.30f,.04f,.04f);
   market_panel(.29f,1.60f,-.12f,.26f,.055f,.11f,.04f,.10f,pose>=.5f?1.f:.30f);
  }else if(kind==9){
   static const float liveries[][3]={{.10f,.13f,.16f},{.21f,.38f,.50f},{.68f,.63f,.52f},{.30f,.30f,.31f},{.47f,.12f,.17f}};
   const float *paint=liveries[(unsigned)p[6]%5];
   market_panel(0,.33f,0,.92f,.49f,2.26f,paint[0],paint[1],paint[2]);
   market_body(0,.91f,-.10f,.87f,.55f,1.42f,.32f,.39f,.43f);
   for(int side=-1;side<=1;side+=2){
    market_panel(side*.92f,.51f,0,.02f,.25f,.93f,.84f,.85f,.81f);
    for(int axle=-1;axle<=1;axle+=2)
     market_body(side*.87f,.35f,axle*1.42f,.14f,.35f,.35f,.11f,.12f,.13f);
   }
   market_panel(-.25f,1.46f,0,.23f,.07f,.11f,pose>=0 && pose<.5f?1.f:.30f,.08f,.09f);
   market_panel(.25f,1.46f,0,.23f,.07f,.11f,.09f,.16f,pose>=.5f?1.f:.32f);
  }else if(kind==8){
   docked_ferry();
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
