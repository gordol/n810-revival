// SPDX-License-Identifier: MIT
// Deterministic cancellation between FRAME send and ACK receive; no GPU needed.
#include <sys/socket.h>
#include <unistd.h>
#include <cassert>
#include <cstdio>
#define GL_GLEXT_PROTOTYPES
#include <GL/gl.h>
#include <GL/glext.h>
extern "C" void glFinish(){}
static ssize_t test_send(int,const void*,size_t,int);
#define send test_send
#include "window_present.h"
#undef send
static int peer=-1;static unsigned releases,closes,publishes,frames;static bool cancel_frame=true;
extern "C" int n810_mbx_window_export(unsigned,n810_runtime::window_image *out){++publishes;*out={2,240,320,1,1,1,0,960};return 0;}
extern "C" int n810_mbx_window_export_release(unsigned,const n810_runtime::window_image*){++releases;return 0;}
static ssize_t test_send(int fd,const void *bytes,size_t size,int flags){
 auto result=::send(fd,bytes,size,flags);const auto &h=*static_cast<const n810_runtime::window_header*>(bytes);
 auto reply=h;reply.width=reply.height=reply.count=reply.reserved=0;
 if(h.kind==n810_runtime::window_frame){
  ++frames;
  if(cancel_frame){cancel_frame=false;n810_runtime::interrupt_window();}
  reply.kind=n810_runtime::window_ack;
 }else {assert(h.kind==n810_runtime::window_begin||h.kind==n810_runtime::window_close);if(h.kind==n810_runtime::window_close)++closes;reply.kind=n810_runtime::window_ready;}
 assert(::send(peer,&reply,sizeof reply,MSG_NOSIGNAL)==sizeof reply);return result;
}
int main(){
 int pair[2];assert(!socketpair(AF_UNIX,SOCK_SEQPACKET,0,pair));peer=pair[1];
 {n810_runtime::window_presenter presenter(pair[0]);bool interrupted=false;
  try{presenter.present(7,240,320);}catch(const std::runtime_error&){interrupted=true;}
  assert(interrupted&&!releases&&!closes);presenter.finish();assert(releases==1&&closes==1);
 }
 assert(releases==1);close(pair[0]);close(pair[1]);
 assert(!socketpair(AF_UNIX,SOCK_SEQPACKET,0,pair));peer=pair[1];
 setenv("N810_SYMBIAN_REUSE_PRESENT","1",1);
 {n810_runtime::window_presenter presenter(pair[0]);
  assert(presenter.present(7,240,320));unsigned p=publishes,f=frames,r=releases;
  for(unsigned i=0;i<20;i++)assert(presenter.present(7,240,320));
  assert(publishes==p&&frames==f&&releases==r);
  presenter.before_write(7);assert(releases==r+1);
  assert(presenter.present(7,240,320));assert(publishes==p+1&&frames==f+1);
  assert(presenter.present(8,240,320));assert(publishes==p+2&&frames==f+2);
  presenter.finish();
 }
 assert(closes==2);close(pair[0]);close(pair[1]);
 std::puts("Cancelled FRAME drains its ACK, waits for CLOSE/READY, then releases exactly once");
}
