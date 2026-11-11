/* SPDX-License-Identifier: MIT. Run against the isolated ARM Mesa, never the device. */
#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <GL/osmesa.h>
#include "mbx_window_export.h"
int main(void){
 int (*begin)(void)=dlsym(RTLD_DEFAULT,"n810_mbx_transaction_begin");
 int (*end)(void)=dlsym(RTLD_DEFAULT,"n810_mbx_transaction_end");
 int (*export_image)(unsigned,struct mbx_window_image*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_export");
 int (*release_image)(unsigned,const struct mbx_window_image*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_export_release");
 int (*import_image)(unsigned,const struct mbx_window_image*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_import");
 int (*forget)(unsigned)=dlsym(RTLD_DEFAULT,"n810_mbx_window_forget");
 int (*get_layout)(struct mbx_window_layout*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_get_layout");
 int (*channels)(unsigned,unsigned,unsigned,unsigned,struct mbx_window_view*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_channels");
 int (*region)(unsigned,unsigned,unsigned,const struct mbx_window_rect*,unsigned,struct mbx_window_view*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_channels_region");
 int (*batch)(unsigned,const struct mbx_window_channel_item*,unsigned,struct mbx_window_view*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_channels_batch");
 assert(begin&&end&&export_image&&release_image&&import_image&&forget&&get_layout&&channels&&region&&batch);
 struct mbx_window_channel_item item={1,2,0,0,1,1,0,0,0};struct mbx_window_view batch_view;assert(batch(3,&item,1,&batch_view)==-ENODEV);
 struct mbx_window_rect rect={0,0,1,1};struct mbx_window_view region_view;assert(region(1,2,3,&rect,0,&region_view)==-ENODEV);
 struct mbx_window_view view;assert(channels(1,2,3,0,&view)==-ENODEV);
 struct mbx_window_layout caps;assert(get_layout(&caps)==-ENODEV);
 assert(!begin()&&!end());struct mbx_window_image image={.version=1,.width=128,.height=128,.format=1,.token={7,11,0}};
 assert(export_image(1,&image)==-ENODEV);assert(import_image(1,&image)==-ENODEV);
 assert(release_image(1,&image)==-ENODEV);assert(forget(1)==-ENODEV);
 OSMesaContext ctx=OSMesaCreateContextExt(OSMESA_RGBA,0,0,0,NULL);assert(ctx);
 unsigned char pixels[16*16*4];assert(OSMesaMakeCurrent(ctx,pixels,GL_UNSIGNED_BYTE,16,16));
 glClearColor(1,0,0,1);glClear(GL_COLOR_BUFFER_BIT);glFinish();
 for(unsigned i=0;i<256;i++)assert(pixels[4*i]==255&&!pixels[4*i+1]&&!pixels[4*i+2]&&pixels[4*i+3]==255);
 assert(import_image(1,&image)==-ENODEV);OSMesaDestroyContext(ctx);
 puts("ARM Mesa: all ten window/transaction symbols exported; no-context/non-GPU rejected; ordinary OSMesa pixels intact");
 return 0;
}
