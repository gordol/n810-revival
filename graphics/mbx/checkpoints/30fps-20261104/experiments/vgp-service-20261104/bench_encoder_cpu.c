#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <stdint.h>
#include "mbx_vgp_isa.c"
#include "mbx_vgp_draw.c"
#include "mbx_vgp_transform.c"
#include "mbx_vgp_wire.c"
static unsigned char input[524288] __attribute__((aligned(4)));
static struct mbx_command c[65536];
static struct mbx_vgp_shader_cache cache;
static uint64_t ns(void){struct timespec t;clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
int main(int argc,char **argv){unsigned n=0,i;uint64_t start,end;FILE *f;size_t bytes;struct mbx_vgp_shader_cache *use;
 if(argc!=3)return 1;f=fopen(argv[1],"rb");if(!f)return 2;bytes=fread(input,1,sizeof(input),f);fclose(f);use=atoi(argv[2])?&cache:NULL;
 for(i=0;i<20;++i)if(mbx_vgp_wire_encode_cached(input,bytes,c,65536,&n,use))return 3;
 start=ns();for(i=0;i<500;++i)if(mbx_vgp_wire_encode_cached(input,bytes,c,65536,&n,use))return 4;end=ns();
 printf("cache=%d words=%u encoder_cpu_us_per_frame=%.3f iterations=500\n",use!=NULL,n,(end-start)/500000.0);return 0;}
