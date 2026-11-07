#define _GNU_SOURCE
#include "../mesa/mbx_trace.h"
#include <pthread.h>
#include <assert.h>
static void *thread(void *unused)
{
 (void)unused;
 for(unsigned i=0;i<128;++i){struct mbx_trace_stamp s=mbx_trace_begin();assert(s.wall);usleep(1000);mbx_trace_end("sleep",s,3);}
 return NULL;
}
int main(void)
{
 setenv("N810_MBX_TRACE","0",1);assert(!mbx_trace_begin().wall);
 setenv("N810_MBX_TRACE","1",1);pthread_t a,b;assert(!pthread_create(&a,NULL,thread,NULL));assert(!pthread_create(&b,NULL,thread,NULL));pthread_join(a,NULL);pthread_join(b,NULL);
 /* Disabled caller retains its cached state and emits no clock samples. */
 assert(!mbx_trace_begin().wall);return 0;
}
