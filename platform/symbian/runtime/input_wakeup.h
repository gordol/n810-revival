// SPDX-License-Identifier: MIT
#pragma once
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <functional>
#include <thread>
#include <poll.h>
#include <sys/eventfd.h>
#include <unistd.h>
inline std::atomic<bool> n810_event_input_active{false};
// Watch inherited input descriptors, but leave all WSERV mutation on its owner
// thread. One notification stays outstanding until that thread drains input.
class n810_input_wakeup {
 int stop_fd_=-1,ack_fd_=-1;std::thread thread_;
 std::atomic<bool> pending_{false};
 static void notify(int fd){std::uint64_t one=1;while(write(fd,&one,sizeof one)<0&&errno==EINTR){}}
 static void consume(int fd){std::uint64_t n;while(read(fd,&n,sizeof n)<0&&errno==EINTR){}}
public:
 n810_input_wakeup(int keyboard,int control,std::function<void()> wake) {
  if(control<0)return;
  stop_fd_=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK);ack_fd_=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK);
  if(stop_fd_<0||ack_fd_<0){stop();return;}
  n810_event_input_active.store(true,std::memory_order_release);
  try {thread_=std::thread([this,keyboard,control,wake]{
   bool first=true;
   for(;;){
    if(!first){pollfd fds[]={{stop_fd_,POLLIN,0},{keyboard,POLLIN,0},{control,POLLIN,0}};
     int n;do{n=poll(fds,3,-1);}while(n<0&&errno==EINTR);
     if(n<0||fds[0].revents)break;
     if((fds[1].revents|fds[2].revents)&(POLLERR|POLLHUP|POLLNVAL))break;
    }
    first=false;pending_.store(true,std::memory_order_release);wake();
    pollfd ack[]={{stop_fd_,POLLIN,0},{ack_fd_,POLLIN,0}};
    int n;do{n=poll(ack,2,-1);}while(n<0&&errno==EINTR);
    if(n<0||ack[0].revents)break;
    consume(ack_fd_);
   }
   n810_event_input_active.store(false,std::memory_order_release);wake();
  });
  } catch(...){stop();}
 }
 bool active()const{return n810_event_input_active.load(std::memory_order_acquire);}
 bool pending()const{return pending_.load(std::memory_order_acquire);}
 void acknowledge(){if(ack_fd_>=0){pending_.store(false,std::memory_order_release);notify(ack_fd_);}}
 void stop(){n810_event_input_active.store(false,std::memory_order_release);if(thread_.joinable()){notify(stop_fd_);thread_.join();}if(stop_fd_>=0){close(stop_fd_);stop_fd_=-1;}if(ack_fd_>=0){close(ack_fd_);ack_fd_=-1;}}
 ~n810_input_wakeup(){stop();}
};
