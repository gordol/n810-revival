/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include "../mesa/mbx_job_lock.h"
static int log_fd,cancel_ready[2];
static void *cancelled_thread(void *arg){
 (void)arg;char marker='Z';assert(!mbx_job_enter());assert(write(log_fd,&marker,1)==1);
 assert(write(cancel_ready[1],&marker,1)==1);struct timespec delay={0,10000000};nanosleep(&delay,NULL);
 assert(write(log_fd,&marker,1)==1);assert(!mbx_job_leave());pthread_testcancel();return NULL;
}
static void *thread(void *arg){
 char id=(char)(uintptr_t)arg;
 for(unsigned i=0;i<12;i++){
  assert(!mbx_job_enter());assert(!mbx_job_enter());
  assert(write(log_fd,&id,1)==1);struct timespec delay={0,1000000};nanosleep(&delay,NULL);
  assert(!mbx_job_leave());assert(write(log_fd,&id,1)==1);assert(!mbx_job_leave());
 }
 return NULL;
}
int main(int argc,char **argv){
 if(argc>1){
  if(!strcmp(argv[1],"crash")){assert(!mbx_job_enter());_exit(0);}
  log_fd=atoi(argv[2]);pthread_t t[2];
  assert(!pthread_create(t,NULL,thread,(void*)(uintptr_t)argv[1][0]));
  assert(!pthread_create(t+1,NULL,thread,(void*)(uintptr_t)(argv[1][0]+1)));
  for(unsigned i=0;i<2;i++)assert(!pthread_join(t[i],NULL));return 0;
 }
 char lock_name[PATH_MAX],log_name[PATH_MAX],fd[32],log[32];
 const char *tmp=getenv("TMPDIR");if(!tmp)tmp="/tmp";
 assert(snprintf(lock_name,sizeof lock_name,"%s/mbx-job-lock-XXXXXX",tmp)<(int)sizeof lock_name);
 assert(snprintf(log_name,sizeof log_name,"%s/mbx-job-log-XXXXXX",tmp)<(int)sizeof log_name);
 int lock=mkstemp(lock_name);assert(lock>=0);unlink(lock_name);
 log_fd=mkstemp(log_name);assert(log_fd>=0);unlink(log_name);
 assert(fcntl(log_fd,F_SETFL,O_APPEND)>=0);snprintf(fd,sizeof fd,"%d",lock);setenv("N810_MBX_JOB_LOCK_FD",fd,1);
 snprintf(log,sizeof log,"%d",log_fd);assert(mbx_job_shared()==1);assert(!mbx_job_enter());assert(!mbx_job_enter());
 pid_t forked=fork();assert(forked>=0);
 if(!forked)_exit(mbx_job_enter()==-ECHILD?0:1);
 int status;assert(waitpid(forked,&status,0)==forked&&WIFEXITED(status)&&!WEXITSTATUS(status));
 assert(!mbx_job_leave());assert(!mbx_job_leave());assert(mbx_job_leave()==-EPERM);
 pid_t children[3];const char *names[]={"A","C","crash"};
 for(unsigned i=0;i<3;i++){
  children[i]=fork();assert(children[i]>=0);
  if(!children[i]){execl(argv[0],argv[0],names[i],log,NULL);_exit(127);}
 }
 for(unsigned i=0;i<3;i++)assert(waitpid(children[i],&status,0)==children[i]&&WIFEXITED(status)&&!WEXITSTATUS(status));
 assert(!mbx_job_enter());assert(!mbx_job_leave());
 assert(pipe(cancel_ready)==0);pthread_t cancelled;assert(!pthread_create(&cancelled,NULL,cancelled_thread,NULL));
 char ready;assert(read(cancel_ready[0],&ready,1)==1);assert(!pthread_cancel(cancelled));void *cancel_result;
 assert(!pthread_join(cancelled,&cancel_result)&&cancel_result==PTHREAD_CANCELED);
 assert(!mbx_job_enter());assert(!mbx_job_leave());close(cancel_ready[0]);close(cancel_ready[1]);
 assert(lseek(log_fd,0,SEEK_SET)==0);char result[100];ssize_t n=read(log_fd,result,sizeof result);assert(n==98);
 for(ssize_t i=0;i<n;i+=2)assert(result[i]==result[i+1]);
 puts("job transaction: dup-inherited FD, processes, threads, nesting, fork rejection, deferred cancellation and exit cleanup passed");
 close(log_fd);close(lock);return 0;
}
