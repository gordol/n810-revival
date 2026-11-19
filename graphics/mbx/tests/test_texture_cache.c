/* SPDX-License-Identifier: MIT */
/* Exercise the CPU reference sampler; production GPU selection is unchanged. */
#include <GL/osmesa.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
static unsigned char texture[256*256*4],pixels[64*64*4];
static void draw(void){
 glClear(GL_COLOR_BUFFER_BIT);
 glBegin(GL_QUADS);
 glTexCoord2f(0,0);glVertex2f(-1,-1);
 glTexCoord2f(1,0);glVertex2f(1,-1);
 glTexCoord2f(1,1);glVertex2f(1,1);
 glTexCoord2f(0,1);glVertex2f(-1,1);
 glEnd();glFinish();
 glReadPixels(0,0,64,64,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
 assert(glGetError()==GL_NO_ERROR);
 for(unsigned y=0;y<64;y++)for(unsigned x=0;x<64;x++)
  for(unsigned c=0;c<4;c++)assert(pixels[(y*64+x)*4+c]==texture[((y*4+2)*256+x*4+2)*4+c]);
}
int main(void){
 OSMesaContext context=OSMesaCreateContextExt(OSMESA_RGBA,0,0,0,NULL);assert(context);
 unsigned char *buffer=calloc(64*64,4);assert(buffer);
 assert(OSMesaMakeCurrent(context,buffer,GL_UNSIGNED_BYTE,64,64));
 glViewport(0,0,64,64);glDisable(GL_DITHER);glEnable(GL_TEXTURE_2D);
 GLuint name;glGenTextures(1,&name);glBindTexture(GL_TEXTURE_2D,name);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
 for(unsigned pass=0;pass<3;pass++){
  for(unsigned y=0;y<256;y++)for(unsigned x=0;x<256;x++){
   unsigned i=(y*256+x)*4;texture[i]=(x/32)*29+pass;
   texture[i+1]=(y/32)*31+pass;texture[i+2]=(x/32+y/32)*13+pass;texture[i+3]=255;
  }
  if(!pass)glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,256,256,0,GL_RGBA,GL_UNSIGNED_BYTE,texture);
  else glTexSubImage2D(GL_TEXTURE_2D,0,0,0,256,256,GL_RGBA,GL_UNSIGNED_BYTE,texture);
  draw();draw(); /* First fill, cache hits/eviction, and texture invalidation. */
 }
 struct rusage usage;assert(!getrusage(RUSAGE_SELF,&usage));
 printf("PASS: texture fill, repeated sampling, eviction and invalidation; peak_rss_kib=%ld\n",usage.ru_maxrss);
 glDeleteTextures(1,&name);OSMesaDestroyContext(context);free(buffer);return 0;
}
