/* SPDX-License-Identifier: MIT. LOCAL TEST ONLY: fake metadata, never renders. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdarg.h>
#include <errno.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/stat.h>
#include "mbx_image_abi.h"
#include "mbx_owned_surface.h"
#include "../mesa/mbx_service_abi.h"
static unsigned test_destination,test_generation=11;
int ioctl(int fd,unsigned long request,...){
 va_list args;va_start(args,request);void *out=va_arg(args,void*);va_end(args);
 if(request==MBX_SERVICE_INFO){*(struct mbx_service_info*)out=(struct mbx_service_info){1,1,1,0};return 0;}
 if(request==MBX_WINDOW_LAYOUT){*(struct mbx_window_layout*)out=(struct mbx_window_layout){2,16,0x3fff,3,240,320,960,MBX_WINDOW_NATIVE_BYTES};return 0;}
 if(request==MBX_SURFACE_ACQUIRE&&getenv("MBX_TEST_DESKTOP")){*(struct mbx_owned_surface*)out=(struct mbx_owned_surface){.version=1,.session=7,.generation=19,.format=MBX_SURFACE_RGB565,.width=getenv("MBX_TEST_DESKTOP_WIDE")?800:400,.height=getenv("MBX_TEST_DESKTOP_WIDE")?480:256,.stride=getenv("MBX_TEST_DESKTOP_WIDE")?1600:800,.bytes=getenv("MBX_TEST_DESKTOP_WIDE")?768000:204800,.flags=MBX_SURFACE_COMPLETE};return 0;}
 if(request==MBX_SURFACE_RELEASE&&getenv("MBX_TEST_DESKTOP"))return 0;
 if(request==MBX_WINDOW_BIND&&getenv("MBX_TEST_CHECKPOINT")){test_destination=((struct mbx_window_request*)out)->destination;test_generation++;return 0;}
 if(request==MBX_WINDOW_QUERY&&getenv("MBX_TEST_CHECKPOINT")){*(struct mbx_window_token*)out=(struct mbx_window_token){7,test_generation,test_destination};return 0;}
 if(request==MBX_WINDOW_QUERY){*(struct mbx_window_token*)out=(struct mbx_window_token){7,11,0};return 0;}
 if(request==MBX_TEXTURE_RESIDENT_INFO){*(struct mbx_texture_resident_info*)out=(struct mbx_texture_resident_info){1,7,0,0};return 0;}
 int (*real_ioctl)(int,unsigned long,...)=dlsym(RTLD_NEXT,"ioctl");
 return real_ioctl(fd,request,out);
}

/* Test-only tripwire: the channels helper must never read any duplicate of
 * its fake GPU file. libc/loader reads of other files remain untouched. */
ssize_t read(int fd,void *buffer,size_t count){
 const char *check=getenv("MBX_TEST_FORBID_GPU_READ"),*gpu=getenv("N810_MBX_RENDER_FD");
 if(check&&gpu){unsigned original=0;for(const char *p=gpu;*p;p++)original=original*10+(*p-'0');struct stat a,b;if(!fstat(fd,&a)&&!fstat(original,&b)&&a.st_dev==b.st_dev&&a.st_ino==b.st_ino)_exit(91);}
 ssize_t (*real_read)(int,void*,size_t)=dlsym(RTLD_NEXT,"read");return real_read(fd,buffer,count);
}
