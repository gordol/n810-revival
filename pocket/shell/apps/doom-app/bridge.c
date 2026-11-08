/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdatomic.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <stdlib.h>
#define PIXELS (320*200)
struct frame { _Atomic uint32_t seq; uint32_t number; uint64_t ns; uint32_t input; uint32_t reserved; uint32_t pixels[PIXELS]; };
static uint64_t now_ns(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
#ifdef ENGINE
#include "doomgeneric.h"
#include "d_event.h"
static struct frame *shared;static uint32_t inputs;
void DG_Init(void){int fd=open(getenv("DOOM_FRAME"),O_RDWR);shared=mmap(0,sizeof(*shared),PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);close(fd);if(shared==MAP_FAILED)exit(2);fcntl(0,F_SETFL,O_NONBLOCK);}
void DG_DrawFrame(void){atomic_fetch_add_explicit(&shared->seq,1,memory_order_seq_cst);memcpy(shared->pixels,DG_ScreenBuffer,PIXELS*4);shared->number++;shared->ns=now_ns();shared->input=inputs;atomic_fetch_add_explicit(&shared->seq,1,memory_order_seq_cst);}
void DG_SleepMs(uint32_t ms){struct timespec t={ms/1000,(ms%1000)*1000000};nanosleep(&t,0);}
uint32_t DG_GetTicksMs(void){return now_ns()/1000000;}
int DG_GetKey(int *pressed,unsigned char *key){
 static unsigned char p[6];static unsigned used;
 event_t mouse={0};mouse.type=ev_mouse;int pending_mouse=0;
 for(unsigned events=0;events<64;++events){
  unsigned size=used>=2&&p[0]==2?6:2;
  if(used<size){ssize_t n=read(0,p+used,size-used);if(n<=0){if(pending_mouse)D_PostEvent(&mouse);return 0;}used+=(unsigned)n;if(used<size){if(pending_mouse)D_PostEvent(&mouse);return 0;}}
  if(p[0]==2){
   if(used<6)continue;
   int dx=(int16_t)((unsigned)p[2]|((unsigned)p[3]<<8));
   int dy=(int16_t)((unsigned)p[4]|((unsigned)p[5]<<8));
   mouse.data1=p[1]&7;mouse.data2+=dx;mouse.data3+=dy;pending_mouse=1;
   if(mouse.data1||dx||dy)inputs++;
   used=0;continue;
  }
  used=0;if(p[0]>1)continue;
  *pressed=p[0];*key=p[1];if(*pressed)inputs++;if(pending_mouse)D_PostEvent(&mouse);return 1;
 }
 if(pending_mouse)D_PostEvent(&mouse);return 0;
}
void DG_SetWindowTitle(const char *s){(void)s;}
int main(int argc,char **argv){doomgeneric_Create(argc,argv);for(;;)doomgeneric_Tick();}
#else
int input_protocol(void){return 2;}
uint64_t bridge_now_ns(void){return now_ns();}
int frame_size(void){return sizeof(struct frame);}
int snapshot(struct frame *source,struct frame *dest){for(int i=0;i<5;i++){uint32_t s=atomic_load_explicit(&source->seq,memory_order_seq_cst);if(s&1)continue;memcpy(dest,source,sizeof(*dest));atomic_thread_fence(memory_order_seq_cst);if(s==atomic_load_explicit(&source->seq,memory_order_seq_cst))return 1;}return 0;}
void convert(struct frame *f,uint64_t *out,int w,int h){for(int y=0;y<h;y++)for(int x=0;x<w;x++){uint32_t a=f->pixels[(y*2*200/(h*2))*320+x*320/w]&0xffffff;uint32_t b=f->pixels[((y*2+1)*200/(h*2))*320+x*320/w]&0xffffff;out[y*w+x]=(1ULL<<48)|((uint64_t)a<<24)|b;}}
int convert_pixels(const struct frame *f,uint16_t *out,size_t capacity,
                   unsigned width,unsigned height,unsigned x0,unsigned y0,
                   unsigned view_width,unsigned view_height)
{
 if(!f||!out||!width||!height||width>4096||height>4096||
    capacity<(size_t)width*height||!view_width||!view_height||
    x0>width||y0>height||view_width>width-x0||view_height>height-y0)return -1;
 memset(out,0,(size_t)width*height*2);
 for(unsigned y=0;y<view_height;++y)for(unsigned x=0;x<view_width;++x){
  uint32_t color=f->pixels[(y*200/view_height)*320+x*320/view_width];
  out[(y+y0)*width+x+x0]=(uint16_t)(((color>>8)&0xf800)|((color>>5)&0x7e0)|((color>>3)&31));
 }
 return 0;
}
#endif
