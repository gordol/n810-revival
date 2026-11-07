/* SPDX-License-Identifier: MIT
 * Optional launcher readiness gate. No GPU access occurs in this helper. */
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>
static int mbx_startup_gate_wait(void)
{
 const char *value=getenv("N810_MBX_READY_FD");
 if(!value)return 0;
 char *end;errno=0;long number=strtol(value,&end,10);
 if(errno||end==value||*end||number<3||number>1048576)return -EINVAL;
 int fd=(int)number,flags=fcntl(fd,F_GETFL);struct stat st;
 if(flags<0||fstat(fd,&st)||!S_ISFIFO(st.st_mode)||(flags&O_ACCMODE)!=O_RDONLY)return -EINVAL;
 unsigned char token=0;ssize_t n;
 do{n=read(fd,&token,1);}while(n<0&&errno==EINTR);
 close(fd);
 return n==1&&token==1?0:-EIO;
}
