#include "utils/includes.h"
#include "utils/common.h"
#include <sys/time.h>
#include <esp_heap_caps.h>
extern int64_t esp_timer_get_time(void);
extern void esp_fill_random(void*,size_t);
int os_get_reltime(struct os_reltime* t){int64_t n=esp_timer_get_time();t->sec=n/1000000;t->usec=n%1000000;return 0;}
int os_get_time(struct os_time* t){struct timeval v;int r=gettimeofday(&v,NULL);t->sec=v.tv_sec;t->usec=v.tv_usec;return r;}
// Caller starts Wi-Fi before constructing the RSN context, enabling full entropy.
int os_get_random(unsigned char* out,size_t n){esp_fill_random(out,n);return 0;}
unsigned long os_random(void){unsigned long n;esp_fill_random(&n,sizeof(n));return n;}
void* pocket_rsn_malloc(size_t n){
 void* p=heap_caps_malloc(n,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 return p?p:heap_caps_malloc(n,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
}
void* pocket_rsn_realloc(void* old,size_t n){
 if(!n){heap_caps_free(old);return NULL;}
 void* p=heap_caps_realloc(old,n,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 return p?p:heap_caps_realloc(old,n,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
}
void pocket_rsn_free(void* p){heap_caps_free(p);}
char* pocket_rsn_strdup(const char* text){size_t n=strlen(text)+1;char* p=pocket_rsn_malloc(n);if(p)memcpy(p,text,n);return p;}
void* os_zalloc(size_t n){void* p=os_malloc(n);if(p)memset(p,0,n);return p;}
void* os_memdup(const void* p,size_t n){void* out=os_malloc(n);if(out)memcpy(out,p,n);return out;}
size_t os_strlcpy(char* out,const char* in,size_t n){size_t z=strlen(in);if(n){size_t c=z<n?z:n-1;memcpy(out,in,c);out[c]=0;}return z;}
int os_memcmp_const(const void* a,const void* b,size_t n){const volatile u8* x=a;const volatile u8* y=b;u8 diff=0;for(size_t i=0;i<n;++i)diff|=x[i]^y[i];return diff;}
