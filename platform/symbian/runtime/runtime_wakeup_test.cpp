// SPDX-License-Identifier: MIT
#include "runtime_wakeup.h"
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <mutex>

static void signal_wake(int){n810_wake_runtime();}

int main(){
    std::mutex mutex;std::condition_variable ready;bool woke=false;
    {
        n810_runtime_wakeup wake([&]{
            std::lock_guard<std::mutex> lock(mutex);woke=true;ready.notify_one();
        });
        std::signal(SIGUSR1,signal_wake);raise(SIGUSR1);
        std::unique_lock<std::mutex> lock(mutex);
        assert(ready.wait_for(lock,std::chrono::seconds(2),[&]{return woke;}));
    }
    assert(n810_runtime_wake_fd==-1);
    raise(SIGUSR1); // A late signal cannot notify an already-destroyed runtime.
}
