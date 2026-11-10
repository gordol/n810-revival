#pragma once
#include <signal.h>
#include <ucontext.h>
#include <fcntl.h>
#include <unistd.h>
#include <cpu/arm_interface.h>
namespace n810_fault {
inline eka2l1::arm::core *cpu=nullptr;
inline void hex(const char *name,unsigned long value) {
    char out[9];const char *digits="0123456789abcdef";
    for(int i=0;i<8;i++)out[i]=digits[(value>>(28-4*i))&15];out[8]='\n';
    unsigned n=0;while(name[n])++n;write(2,name,n);write(2,out,9);
}
inline void capture(int signal,siginfo_t *,void *opaque) {
    auto *context=static_cast<ucontext_t *>(opaque);
    hex("native_fault_signal=",signal);
    hex("native_fault_pc=",context->uc_mcontext.arm_pc);
    hex("native_fault_lr=",context->uc_mcontext.arm_lr);
    hex("native_fault_cpsr=",context->uc_mcontext.arm_cpsr);
    hex("native_fault_sp=",context->uc_mcontext.arm_sp);
    hex("native_r0=",context->uc_mcontext.arm_r0);
    hex("native_r1=",context->uc_mcontext.arm_r1);
    hex("native_r2=",context->uc_mcontext.arm_r2);
    hex("native_r3=",context->uc_mcontext.arm_r3);
    hex("native_r4=",context->uc_mcontext.arm_r4);
    hex("native_r5=",context->uc_mcontext.arm_r5);
    hex("native_r6=",context->uc_mcontext.arm_r6);
    hex("native_r7=",context->uc_mcontext.arm_r7);
    hex("native_r8=",context->uc_mcontext.arm_r8);
    hex("native_r9=",context->uc_mcontext.arm_r9);
    hex("native_r10=",context->uc_mcontext.arm_r10);
    if(cpu) {hex("guest_pc=",cpu->get_pc());hex("guest_lr=",cpu->get_reg(14));hex("guest_cpsr=",cpu->get_cpsr());}
    int fd=open("/proc/self/maps",O_RDONLY);char buffer[4096];ssize_t size;
    while(fd>=0 && (size=read(fd,buffer,sizeof(buffer)))>0)write(2,buffer,size);
    if(fd>=0)close(fd);_exit(128+signal);
}
inline void install() {
    struct sigaction action{};action.sa_sigaction=capture;action.sa_flags=SA_SIGINFO;
    sigemptyset(&action.sa_mask);
    for(int signal : {SIGILL,SIGSEGV,SIGBUS})sigaction(signal,&action,nullptr);
}
}
