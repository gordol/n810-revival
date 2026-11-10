// SPDX-License-Identifier: MIT
#pragma once
#include <sys/inotify.h>
#include <unistd.h>
#include <poll.h>
#include <cstring>
#include <cerrno>
// Observe the private app-control file without reopening it on every guest slice.
// Physical keyboard ownership remains with the existing inherited descriptor.
class n810_control_watch {
 int fd_=-1;bool first_=true;
public:
 n810_control_watch(){fd_=inotify_init1(IN_NONBLOCK|IN_CLOEXEC);if(fd_>=0&&inotify_add_watch(fd_,".",IN_CLOSE_WRITE|IN_MOVED_TO|IN_CREATE)<0){close(fd_);fd_=-1;}}
 ~n810_control_watch(){if(fd_>=0)close(fd_);}
 int fd()const{return fd_;}
 bool pending(){
  bool ready=first_;first_=false;
  if(fd_<0)return true; // Preserve the old bounded control reader on failure.
  alignas(inotify_event) char events[4096];
  for(;;){ssize_t n=read(fd_,events,sizeof events);if(n<0){if(errno==EINTR)continue;break;}if(!n)break;
   for(size_t at=0;at<static_cast<size_t>(n);){const auto *e=reinterpret_cast<const inotify_event*>(events+at);if(e->mask&IN_Q_OVERFLOW)ready=true;if(e->len&&!std::strcmp(e->name,"control-keys"))ready=true;at+=sizeof(*e)+e->len;}
  }
  return ready;
 }
};
