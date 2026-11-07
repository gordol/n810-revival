/* SPDX-License-Identifier: MIT */
#define main status_window_main
#include "../mesa/gears_status.c"
#undef main
#include <assert.h>
int main(void)
{
 assert(!line("N810_MBX_GPU_FRAME triangles=388 GPU_jobs=1 CPU_raster_triangles=9"));
 assert(!strcmp(mode,"Preparing graphics"));
 assert(!line("N810_MBX_GPU_FRAME triangles=388 GPU_jobs=1"));
 assert(!line("N810_MBX_GPU_FRAME triangles=388 GPU_jobs=1 CPU_raster_triangles=0 junk"));
 assert(line("N810_MBX_GPU_FRAME triangles=388 GPU_jobs=1 CPU_raster_triangles=0"));
 assert(!strcmp(mode,"GPU raster: verified"));assert(!strcmp(jobs,"Batch: 388 triangles"));
 assert(line("150 frames in 5.000 seconds = 30.000 FPS"));
 assert(strstr(fps,"30.000"));
 assert(line("N810_MBX_GPU_FRAME completed=150 GPU_jobs=1 CPU_raster_triangles=0 async=1"));
 assert(!strcmp(jobs,"GPU completed: 150"));
 assert(line("N810_MBX_GPU_FAILED"));assert(strstr(mode,"FAILED"));
 puts("PASS status rejects incomplete/contradictory completion records and reports measured FPS, frame batch and failure");
}
