"""Exercise the actual native readiness gate, without a GPU or application edits."""
from pathlib import Path
import subprocess,tempfile
header=Path(__file__).resolve().parents[1]/'mesa/mbx_startup_gate.h'
code=r'''
#include <assert.h>
#include <stdio.h>
#include <sys/wait.h>
#include <time.h>
#include "HEADER"
static void trial(int token,int expected){
 int p[2];assert(!pipe(p));pid_t child=fork();assert(child>=0);
 if(!child){close(p[1]);char value[32];snprintf(value,sizeof value,"%d",p[0]);setenv("N810_MBX_READY_FD",value,1);_exit(mbx_startup_gate_wait()==expected?0:1);}
 close(p[0]);struct timespec delay={0,30000000};nanosleep(&delay,NULL);
 int status;assert(waitpid(child,&status,WNOHANG)==0);
 if(token>=0){unsigned char b=token;assert(write(p[1],&b,1)==1);}close(p[1]);
 assert(waitpid(child,&status,0)==child && WIFEXITED(status)&&WEXITSTATUS(status)==0);
}
int main(void){
 unsetenv("N810_MBX_READY_FD");assert(mbx_startup_gate_wait()==0);
 setenv("N810_MBX_READY_FD","bad",1);assert(mbx_startup_gate_wait()==-EINVAL);
 setenv("N810_MBX_READY_FD","0",1);assert(mbx_startup_gate_wait()==-EINVAL);
 trial(1,0);trial(0,-EIO);trial(-1,-EIO);
 puts("PASS: gate blocks until verified token, rejects failure/EOF/invalid descriptor, and is optional");
}
'''.replace('HEADER',str(header))
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'gate.c').write_text(code)
 subprocess.run(['cc','-O1','-fsanitize=address,undefined','-o',str(p/'gate'),str(p/'gate.c')],check=True)
 subprocess.run([str(p/'gate')],check=True)
