#include <GL/osmesa.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <time.h>
int main(void) {
 const int a[]={OSMESA_FORMAT,OSMESA_RGBA,OSMESA_PROFILE,OSMESA_CORE_PROFILE,OSMESA_CONTEXT_MAJOR_VERSION,3,OSMESA_CONTEXT_MINOR_VERSION,3,0};
 struct timespec start,end;clock_gettime(CLOCK_MONOTONIC,&start);
 OSMesaContext c=OSMesaCreateContextAttribs(a,NULL);if(!c)return 2;
 unsigned char *p=calloc(240*320,4);if(!p||!OSMesaMakeCurrent(c,p,GL_UNSIGNED_BYTE,240,320))return 3;
 OSMesaPixelStore(OSMESA_Y_UP,0);glEnable(GL_SCISSOR_TEST);
 const unsigned char colors[4][4]={{255,0,0,255},{0,255,0,255},{0,0,255,255},{255,255,255,255}};
 for(int i=0;i<4;i++){glScissor((i%2)*120,(i/2)*160,120,160);glClearColor(colors[i][0]/255.f,colors[i][1]/255.f,colors[i][2]/255.f,1);glClear(GL_COLOR_BUFFER_BIT);}
 glFinish();unsigned errors=0;
 for(int y=0;y<320;y++)for(int x=0;x<240;x++)for(int k=0;k<4;k++)if(p[(y*240+x)*4+k]!=colors[((319-y)/160)*2+x/120][k])errors++;
 clock_gettime(CLOCK_MONOTONIC,&end);struct rusage u;getrusage(RUSAGE_SELF,&u);
 printf("renderer=%s pixel_component_mismatches=%u elapsed_ms=%.3f peak_rss_kib=%ld\n",glGetString(GL_RENDERER),errors,(end.tv_sec-start.tv_sec)*1000.+(end.tv_nsec-start.tv_nsec)/1e6,u.ru_maxrss);
 OSMesaDestroyContext(c);free(p);return errors?4:0;
}
