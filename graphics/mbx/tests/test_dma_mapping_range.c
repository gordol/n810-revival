/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#define PAGE_SIZE 4096U
#define DIV_ROUND_UP(n,d) (((n)+(d)-1)/(d))
#define EINVAL 22
static int range(unsigned x,unsigned y,unsigned w,unsigned h,unsigned dx,unsigned dy,int reverse){
 struct {struct {unsigned stride;}surface;unsigned x,y,width,height,destination_x,destination_y,stride;} storage={{1600},x,y,w,h,dx,dy,1600},*q=&storage;
 unsigned ns=188,nd=188,sfirst=0,slast=0,dfirst=0,dlast=0;int gpu_dma_damage_mapping=1,error=0;
/* ACTUAL_MAPPING_RANGE */
 for(unsigned row=0;row<h;row++)for(unsigned col=0;col<w*2;col++){
  size_t so=(size_t)(y+(reverse?h-1-row:row))*1600+x*2+col,to=(size_t)(dy+row)*1600+dx*2+col;
  assert(so/PAGE_SIZE>=sfirst&&so/PAGE_SIZE<slast);assert(to/PAGE_SIZE>=dfirst&&to/PAGE_SIZE<dlast);
 }
 return 0;
 out:return error;
}
int main(void){for(unsigned i=0;i<200;i++){unsigned w=1+i%211,h=1+i%71,x=(i*17)%(801-w),y=(i*23)%(481-h),dx=(i*31)%(801-w),dy=(i*47)%(481-h);assert(!range(x,y,w,h,dx,dy,i&1));}assert(!range(0,0,800,480,0,0,0));}
