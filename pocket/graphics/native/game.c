/* SPDX-License-Identifier: MIT */
#include <math.h>
struct target {float x,y,z;int broken;};
static struct target targets[]={{0,320,900,0},{-430,320,1800,0},{430,320,2600,0}};
static float flash_until,game_time;
static int game_enabled;
void pocket_game_enable(int enabled){game_enabled=!!enabled;}
static unsigned shots,hits;
void pocket_game_reset(void){for(unsigned i=0;i<3;i++)targets[i].broken=0;shots=hits=0;flash_until=0;}
unsigned pocket_game_hits(void){return hits;}
int pocket_game_fire(float x,float y,float z,float yaw,float pitch){
 if(!isfinite(x)||!isfinite(y)||!isfinite(z)||!isfinite(yaw)||!isfinite(pitch))return -1;
 float ce=cosf(.05f+pitch),dx=sinf(yaw)*ce,dy=-sinf(.05f+pitch),dz=cosf(yaw)*ce;
 int nearest=-1;float distance=100000;
 for(unsigned i=0;i<3;i++)if(!targets[i].broken){
  float vx=targets[i].x-x,vy=targets[i].y-y,vz=targets[i].z-z;
  float t=vx*dx+vy*dy+vz*dz;
  float offset=vx*vx+vy*vy+vz*vz-t*t;
  if(t>0&&offset<110*110&&t<distance){distance=t;nearest=(int)i;}
 }
 ++shots;flash_until=game_time+.09f;
 if(nearest>=0){targets[nearest].broken=1;++hits;return 1;}
 return 0;
}
static void game_quad(float x,float y,float w,float h,float z,float r,float g,float b){
 const float v[]={x,y,z,x+w,y,z,x,y+h,z,x+w,y,z,x+w,y+h,z,x,y+h,z};
 glColor3f(r,g,b);glVertexPointer(3,GL_FLOAT,0,v);glDrawArrays(GL_TRIANGLES,0,6);
}
static void game_draw(float age,unsigned width,unsigned height,unsigned tx,unsigned ty,unsigned tw,unsigned th){
 if(!game_enabled)return;
 glPushAttrib(GL_ALL_ATTRIB_BITS);glPushClientAttrib(GL_CLIENT_ALL_ATTRIB_BITS);
 game_time=age;
 glDisable(GL_LIGHTING);glDisable(GL_TEXTURE_2D);glDisable(GL_VERTEX_PROGRAM_ARB);
 glDisableClientState(GL_COLOR_ARRAY);glDisableClientState(GL_NORMAL_ARRAY);glEnableClientState(GL_VERTEX_ARRAY);
 for(unsigned i=0;i<3;i++)if(!targets[i].broken){
  struct target t=targets[i];
  game_quad(t.x-90,t.y-90,180,180,t.z,1,.25f,.06f);
  game_quad(t.x-30,t.y-30,60,60,t.z-1,1,1,.5f);
 }
 glViewport(0,400-(int)th,tw,th);
 glDisable(GL_DEPTH_TEST);glMatrixMode(GL_PROJECTION);glPushMatrix();glLoadIdentity();
 glOrtho(tx,tx+tw,height-ty-th,height-ty,-1,1);glMatrixMode(GL_MODELVIEW);glPushMatrix();glLoadIdentity();
 float cx=width*.5f,cy=height*.5f;
 game_quad(cx-6,cy-1,12,2,0,.8f,1,.8f);game_quad(cx-1,cy-6,2,12,0,.8f,1,.8f);
 float recoil=age<flash_until?-8:0;
 game_quad(cx+16,0,42,75+recoil,0,.15f,.18f,.2f);
 game_quad(cx+25,60+recoil,24,80,0,.35f,.4f,.43f);
 if(age<flash_until){game_quad(cx+18,139+recoil,38,25,0,1,.7f,.1f);}
 /* Remaining target markers stay readable without a separate text renderer. */
 for(unsigned i=0;i<3;i++)game_quad(8+i*14,height-18,10,10,0,targets[i].broken?.1f:1,targets[i].broken?.8f:.3f,.1f);
 glPopMatrix();glMatrixMode(GL_PROJECTION);glPopMatrix();glMatrixMode(GL_MODELVIEW);
 glPopClientAttrib();glPopAttrib();
}
