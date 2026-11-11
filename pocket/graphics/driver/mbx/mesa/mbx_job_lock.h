/* SPDX-License-Identifier: MIT
 * Cooperative clients share one render OFD and one regular lock-file inode.
 * POSIX record locks are process-owned: unlike flock/OFD locks they still
 * exclude a second process holding a dup/SCM_RIGHTS copy of the same FD.
 * The local mutex also excludes other threads. Configure before first use;
 * forked children must exec before entering Mesa.
 */
#ifndef MBX_JOB_LOCK_H
#define MBX_JOB_LOCK_H
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>
static pthread_once_t mbx_job_once=PTHREAD_ONCE_INIT;
static pthread_mutex_t mbx_job_mutex=PTHREAD_MUTEX_INITIALIZER;
static int mbx_job_fd=-1,mbx_job_error;
static pid_t mbx_job_pid;
static _Thread_local unsigned mbx_job_depth;
static _Thread_local int mbx_job_cancelstate;
static void mbx_job_initialize(void){
 const char *text=getenv("N810_MBX_JOB_LOCK_FD");char *end;long fd;struct stat st;
 mbx_job_pid=getpid();if(!text)return;
 errno=0;fd=strtol(text,&end,10);
 if(!*text||*end||errno||fd<0||fd>INT_MAX){mbx_job_error=EINVAL;return;}
 if(fstat((int)fd,&st)||!S_ISREG(st.st_mode)||
    (fcntl((int)fd,F_GETFL)&O_ACCMODE)!=O_RDWR){mbx_job_error=EINVAL;return;}
 mbx_job_fd=fcntl((int)fd,F_DUPFD_CLOEXEC,3);
 if(mbx_job_fd<0)mbx_job_error=errno;
}
static inline int mbx_job_shared(void){
 pthread_once(&mbx_job_once,mbx_job_initialize);
 if(mbx_job_pid!=getpid())return -ECHILD;
 return mbx_job_error?-mbx_job_error:mbx_job_fd>=0;
}
static inline int mbx_job_enter(void){
 struct flock lock={.l_type=F_WRLCK,.l_whence=SEEK_SET,.l_start=0,.l_len=1};
 int shared=mbx_job_shared(),error;
 if(shared<=0)return shared;
 if(mbx_job_depth){if(mbx_job_depth==UINT_MAX)return -EOVERFLOW;++mbx_job_depth;return 0;}
 error=pthread_setcancelstate(PTHREAD_CANCEL_DISABLE,&mbx_job_cancelstate);if(error)return -error;
 error=pthread_mutex_lock(&mbx_job_mutex);if(error){pthread_setcancelstate(mbx_job_cancelstate,NULL);return -error;}
 while(fcntl(mbx_job_fd,F_SETLKW,&lock)<0){
  if(errno==EINTR)continue;
  error=errno;pthread_mutex_unlock(&mbx_job_mutex);pthread_setcancelstate(mbx_job_cancelstate,NULL);return -error;
 }
 mbx_job_depth=1;return 0;
}
static inline int mbx_job_leave(void){
 struct flock lock={.l_type=F_UNLCK,.l_whence=SEEK_SET,.l_start=0,.l_len=1};
 int shared=mbx_job_shared(),error=0;
 if(shared<=0)return shared;
 if(!mbx_job_depth)return -EPERM;
 if(--mbx_job_depth)return 0;
 if(fcntl(mbx_job_fd,F_SETLK,&lock)<0)error=errno;
 {int unlocked=pthread_mutex_unlock(&mbx_job_mutex);if(!error)error=unlocked;}
 {int restored=pthread_setcancelstate(mbx_job_cancelstate,NULL);if(!error)error=restored;}
 return -error;
}
#endif
