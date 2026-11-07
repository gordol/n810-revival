#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
void *pocket_mbx_open(int);int pocket_mbx_stage(void*,unsigned,const unsigned char*,unsigned,unsigned);int pocket_mbx_render(void*,uint16_t*);unsigned pocket_mbx_jobs(void*);void pocket_mbx_close(void*);const char *pocket_mbx_error(void);
int main(int argc,char **argv){
 if(argc!=5)return 2;
 int gpu=strcmp(argv[4],"reference")!=0;
 FILE *f=fopen(argv[1],"rb");if(!f)return 3;unsigned char cells[60000];if(fread(cells,1,sizeof(cells),f)!=sizeof(cells)||fgetc(f)!=EOF)return 3;fclose(f);
 uint16_t *actual=calloc(384000,2),*expected=malloc(768000);if(!actual||!expected)return 3;
 f=fopen(argv[2],"rb");if(!f||fread(expected,1,768000,f)!=768000)return 3;fclose(f);
 void *r=pocket_mbx_open(gpu);if(!r){fprintf(stderr,"%s\n",pocket_mbx_error());return 4;}
 for(unsigned i=0;i<3000;++i){unsigned char *p=cells+20*i;unsigned fg=p[0]|p[1]<<8,bg=p[2]|p[3]<<8;if(pocket_mbx_stage(r,i,p+4,fg,bg))return 5;}
 if(pocket_mbx_render(r,actual)){fprintf(stderr,"%s\n",pocket_mbx_error());return 6;}
 unsigned changed=0;for(unsigned i=0;i<384000;++i)changed+=actual[i]!=expected[i];
 printf("require_gpu=%d changed_pixels=%u render_jobs=%u\n",gpu,changed,pocket_mbx_jobs(r));
 f=fopen(argv[3],"wb");if(!f||fwrite(actual,1,768000,f)!=768000)return 7;fclose(f);
 unsigned jobs=pocket_mbx_jobs(r);if(pocket_mbx_render(r,actual)||jobs!=pocket_mbx_jobs(r))return 8;
 pocket_mbx_close(r);free(actual);free(expected);return changed?9:0;
}
