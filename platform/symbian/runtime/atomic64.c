/* Process-local 64-bit atomics for the N810 runtime. The installed kernel's
 * __kuser_cmpxchg64 faults on this device. Link wrapping confines this fallback
 * to our executable; no system library, kernel, or GPU code is replaced.
 * All three operations used by the linked runtime share one mutex. */
#include <pthread.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
static pthread_mutex_t atomic64_lock=PTHREAD_MUTEX_INITIALIZER;
static void lock(void) { if(pthread_mutex_lock(&atomic64_lock))abort(); }
static void unlock(void) { if(pthread_mutex_unlock(&atomic64_lock))abort(); }
uint64_t __wrap___atomic_load_8(const volatile void *p,int order) {
 (void)order;uint64_t value;lock();memcpy(&value,(const void *)p,8);unlock();return value;
}
uint64_t __wrap___atomic_fetch_add_8(volatile void *p,uint64_t amount,int order) {
 (void)order;uint64_t old,value;lock();memcpy(&old,(const void *)p,8);value=old+amount;memcpy((void *)p,&value,8);unlock();return old;
}
uint64_t __wrap___atomic_fetch_sub_8(volatile void *p,uint64_t amount,int order) {
 return __wrap___atomic_fetch_add_8(p,0-amount,order);
}
