/* SPDX-License-Identifier: MIT. Explicit final-target export, thread confined.
 * Begin immediately before glFinish; exactly one RGB565 job must complete.
 * The borrowed kernel image cannot be overwritten until release succeeds.
 */
#include "mbx_owned_surface.h"
int n810_mbx_surface_begin(void);
int n810_mbx_surface_end(struct mbx_owned_surface *);
int n810_mbx_surface_copy(const struct mbx_surface_sink *);
int n810_mbx_surface_dma_copy(const struct mbx_surface_dma_sink *);
int n810_mbx_surface_release(void);
static _Thread_local struct { unsigned armed,held; int fd; struct mbx_owned_surface image; } mbx_export;
__attribute__((visibility("default"))) int n810_mbx_surface_begin(void){
 if(mbx_export.armed||mbx_export.held)return -1;
 int error=mbx_job_enter();if(error)return error;
 mbx_export.armed=1;mbx_export.fd=-1;return 0;
}
__attribute__((visibility("default"))) int n810_mbx_surface_end(struct mbx_owned_surface *out){
 if(!out||!mbx_export.armed||!mbx_export.held)return -1;
 *out=mbx_export.image;mbx_export.armed=0;return 0;
}
__attribute__((visibility("default"))) int n810_mbx_surface_copy(const struct mbx_surface_sink *sink){
 if(!sink||mbx_export.armed||!mbx_export.held)return -1;
 return ioctl(mbx_export.fd,MBX_SURFACE_COPY_SINK,sink);
}
__attribute__((visibility("default"))) int n810_mbx_surface_dma_copy(const struct mbx_surface_dma_sink *sink){
 if(!sink||mbx_export.armed||!mbx_export.held)return -1;
 return ioctl(mbx_export.fd,MBX_SURFACE_DMA_SINK,sink);
}
__attribute__((visibility("default"))) int n810_mbx_surface_release(void){
 if(!mbx_export.held){if(!mbx_export.armed)return 0;mbx_export.armed=0;return mbx_job_leave();}
 if(ioctl(mbx_export.fd,MBX_SURFACE_RELEASE,&mbx_export.image))return -1;
 close(mbx_export.fd);
 memset(&mbx_export,0,sizeof(mbx_export));mbx_export.fd=-1;return mbx_job_leave();
}
