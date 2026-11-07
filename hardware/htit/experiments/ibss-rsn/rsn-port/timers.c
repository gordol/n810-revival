// Bounded, single-threaded timer adapter. No sockets, threads or signal handlers.
#include "utils/includes.h"
#include "utils/common.h"
#include "utils/eloop.h"
#include <stdint.h>

struct timer { uint64_t due; eloop_timeout_handler fn; void *a,*b; };
static struct timer timers[64];
static uint64_t now(void) {
    struct os_reltime t;
    if(os_get_reltime(&t))abort();
    return (uint64_t)t.sec*1000000+t.usec;
}
static int matches(struct timer* t,eloop_timeout_handler f,void* a,void* b) {
    return t->fn==f && (a==ELOOP_ALL_CTX || t->a==a) && (b==ELOOP_ALL_CTX || t->b==b);
}
int eloop_register_timeout(unsigned s,unsigned us,eloop_timeout_handler f,void* a,void* b) {
    if(!f)return -1;
    for(unsigned i=0;i<64;++i)if(!timers[i].fn) {
        timers[i]=(struct timer){now()+(uint64_t)s*1000000+us,f,a,b};return 0;
    }
    return -1;
}
int eloop_cancel_timeout(eloop_timeout_handler f,void* a,void* b) {
    int count=0;
    for(unsigned i=0;i<64;++i)if(matches(&timers[i],f,a,b)){timers[i].fn=NULL;++count;}
    return count;
}
int eloop_is_timeout_registered(eloop_timeout_handler f,void* a,void* b) {
    for(unsigned i=0;i<64;++i)if(matches(&timers[i],f,a,b))return 1;
    return 0;
}
int eloop_cancel_timeout_one(eloop_timeout_handler f,void* a,void* b,struct os_reltime* left) {
    for(unsigned i=0;i<64;++i)if(matches(&timers[i],f,a,b)) {
        uint64_t n=now(),us=timers[i].due>n?timers[i].due-n:0;
        if(left){left->sec=us/1000000;left->usec=us%1000000;}
        timers[i].fn=NULL;return 1;
    }
    if(left)memset(left,0,sizeof(*left));return 0;
}
static int adjust(unsigned s,unsigned us,eloop_timeout_handler f,void* a,void* b,int replenish) {
    for(unsigned i=0;i<64;++i)if(matches(&timers[i],f,a,b)) {
        uint64_t due=now()+(uint64_t)s*1000000+us;
        if(replenish?due>timers[i].due:due<timers[i].due){timers[i].due=due;return 1;}
        return 0;
    }
    return -1;
}
int eloop_deplete_timeout(unsigned s,unsigned us,eloop_timeout_handler f,void* a,void* b) {return adjust(s,us,f,a,b,0);}
int eloop_replenish_timeout(unsigned s,unsigned us,eloop_timeout_handler f,void* a,void* b) {return adjust(s,us,f,a,b,1);}
void pocket_eloop_poll(void) {
    // Limit callback work per invocation; new immediately due timers wait their turn.
    for(unsigned n=0;n<16;++n) {
        unsigned selected=64;uint64_t at=now();
        for(unsigned i=0;i<64;++i)if(timers[i].fn && timers[i].due<=at &&
            (selected==64 || timers[i].due<timers[selected].due))selected=i;
        if(selected==64)break;
        struct timer t=timers[selected];timers[selected].fn=NULL;t.fn(t.a,t.b);
    }
}
