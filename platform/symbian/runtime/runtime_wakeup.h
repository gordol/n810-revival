// SPDX-License-Identifier: MIT
#pragma once
#include <atomic>
#include <cerrno>
#include <csignal>
#include <cstdint>
#include <functional>
#include <stdexcept>
#include <thread>
#include <poll.h>
#include <sys/eventfd.h>
#include <unistd.h>

inline volatile std::sig_atomic_t n810_runtime_wake_fd=-1;
inline void n810_wake_runtime() noexcept {
    const int saved_errno=errno;
    const int fd=n810_runtime_wake_fd;
    if(fd>=0){const std::uint64_t one=1;const auto result=write(fd,&one,sizeof(one));(void)result;}
    errno=saved_errno;
}

// Wake a sleeping guest scheduler from signals and graphics failures. The
// signal handler only writes an eventfd; kernel locks stay on this thread.
class n810_runtime_wakeup {
    int fd_;std::atomic<bool> stopping_{false};std::thread thread_;
public:
    explicit n810_runtime_wakeup(std::function<void()> wake):fd_(eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK)) {
        if(fd_<0)throw std::runtime_error("Runtime wake eventfd failed");
        thread_=std::thread([this,wake]{
            for(;;){
                pollfd ready{fd_,POLLIN,0};int result;
                do{result=poll(&ready,1,-1);}while(result<0&&errno==EINTR);
                if(result<=0)return;
                std::uint64_t count;while(read(fd_,&count,sizeof(count))<0&&errno==EINTR){}
                if(stopping_.load(std::memory_order_acquire))return;
                wake();
            }
        });
        n810_runtime_wake_fd=fd_;
    }
    ~n810_runtime_wakeup(){
        n810_runtime_wake_fd=-1;stopping_.store(true,std::memory_order_release);
        const std::uint64_t one=1;const auto result=write(fd_,&one,sizeof(one));(void)result;
        thread_.join();
        // A signal handler may already have loaded the descriptor. Keep this
        // one bounded descriptor alive until exit so it cannot hit a reused fd.
    }
};
