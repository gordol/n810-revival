#pragma once
#include "runtime_debug.h"
#include <kernel/kernel.h>
#include <kernel/thread.h>
#include <kernel/process.h>
#include <kernel/ipc.h>
#include <kernel/timing.h>
#include <array>
#include <condition_variable>
#include <cstring>
#include <mutex>
#include <thread>
#include <cstdio>
#include <vector>
#include <unistd.h>
// Wake the host loop only: no guest request is completed or fabricated. This
// lets keyboard/frontend callbacks and the bounded deadline run while EKA2 idles.
class runtime_diagnostics {
    eka2l1::kernel_system *kernel_;
    struct ipc_entry {unsigned long long thread;unsigned request;int opcode;bool completed;char server[64];};
    std::array<ipc_entry,256> recent_{};
    std::size_t sends_=0,callback_=0,complete_callback_=0;
    struct completion {unsigned long long thread;unsigned request;int opcode,result;};
    std::array<completion,16> completed_{};std::size_t completions_=0;
    std::mutex mutex_;std::condition_variable cv_;bool done_=false;std::thread wake_;
public:
    explicit runtime_diagnostics(eka2l1::kernel_system *kernel):kernel_(kernel) {
        if(n810_runtime_debug()) {
        callback_=kernel_->register_ipc_send_callback([this](const std::string &server,int opcode,const eka2l1::ipc_arg &,address request,eka2l1::kernel::thread *thread) {
            auto &entry=recent_[sends_++%recent_.size()];entry.thread=thread?thread->unique_id():0;entry.request=request;entry.opcode=opcode;entry.completed=false;
            std::strncpy(entry.server,server.c_str(),sizeof(entry.server)-1);entry.server[sizeof(entry.server)-1]=0;
        });
        complete_callback_=kernel_->register_ipc_complete_callback([this](eka2l1::ipc_msg *msg,int result) {
            const auto begin=sends_>recent_.size()?sends_-recent_.size():0;
            for(auto i=sends_;i>begin;--i) {auto &entry=recent_[(i-1)%recent_.size()];
                if(msg->own_thr && entry.thread==msg->own_thr->unique_id() && entry.request==msg->request_sts.ptr_address()) {
                    entry.completed=true;break;}}
            completed_[completions_++%completed_.size()]={msg->own_thr?msg->own_thr->unique_id():0,msg->request_sts.ptr_address(),msg->function,result};
        });
        }
        wake_=std::thread([this] {
            std::unique_lock<std::mutex> lock(mutex_);
            while(!cv_.wait_for(lock,std::chrono::milliseconds(100),[this]{return done_;})) {
                lock.unlock();kernel_->stop_cores_idling();lock.lock();
            }
        });
    }
    ~runtime_diagnostics() {
        if(n810_runtime_debug()) std::fprintf(stderr,"runtime_teardown=diagnostic_wake_join\n");
        {std::lock_guard<std::mutex> lock(mutex_);done_=true;}cv_.notify_all();wake_.join();
        if(n810_runtime_debug()) std::fprintf(stderr,"runtime_teardown=diagnostic_callbacks\n");
        if(n810_runtime_debug()) kernel_->unregister_ipc_send_callback(callback_);
        if(n810_runtime_debug()) kernel_->unregister_ipc_complete_callback(complete_callback_);
    }
    void dump() {
        if(!n810_runtime_debug())return;
        eka2l1::kernel_lock lock(kernel_);
        unsigned count=0;
        for(auto &object:kernel_->get_thread_list()) {
            if(!object || count++>=12)continue;
            auto *thread=static_cast<eka2l1::kernel::thread *>(object.get());
            const auto &registers=thread->get_thread_context().cpu_registers;
            if(registers[14]==0x803a8b95) {
                auto *status=eka2l1::ptr<eka2l1::epoc::request_status>(registers[5]).get(thread->owning_process());
                auto *return_address=eka2l1::ptr<std::uint32_t>(registers[13]+12).get(thread->owning_process());
                std::printf("guest_specific_wait thread=%llu r5=%08x status=%08x flags=%08x sp=%08x return=%08x\n",
                    static_cast<unsigned long long>(thread->unique_id()),registers[5],status?status->status:0,status?status->flags:0,registers[13],return_address?*return_address:0);
            }
            std::printf("guest_thread name=%s state=%d pc=%08x lr=%08x request_count=%d wait=%s\n",thread->name().c_str(),static_cast<int>(thread->current_state()),
                thread->get_thread_context().cpu_registers[15],thread->get_thread_context().cpu_registers[14],thread->request_count(),thread->wait_obj?thread->wait_obj->name().c_str():"none");
        }
        for(auto &object:kernel_->get_thread_list()) {
            if(!object)continue;
            auto *thread=static_cast<eka2l1::kernel::thread *>(object.get());
            unsigned pending=0;
            const auto begin=sends_>recent_.size()?sends_-recent_.size():0;
            for(auto i=begin;i<sends_;++i) {
                auto &entry=recent_[i%recent_.size()];
                if(entry.thread!=thread->unique_id() || !entry.request || entry.completed)continue;
                bool superseded=false;
                for(auto j=i+1;j<sends_;++j) {auto &later=recent_[j%recent_.size()];
                    if(later.thread==entry.thread && later.request==entry.request){superseded=true;break;}}
                if(superseded)continue;
                auto *status=eka2l1::ptr<eka2l1::epoc::request_status>(entry.request).get(thread->owning_process());
                if(status && status->status==eka2l1::epoc::request_status::pending_status && pending++<12)
                    std::printf("pending_ipc thread=%llu server=%s opcode=%d request=%08x flags=%x\n",entry.thread,entry.server,entry.opcode,entry.request,status->flags);
            }
        }
        for(auto i=completions_>6?completions_-6:0;i<completions_;++i) {auto &entry=completed_[i%completed_.size()];
            std::printf("completed_ipc thread=%llu opcode=%d request=%08x result=%d\n",entry.thread,entry.opcode,entry.request,entry.result);}
        // Read-only, bounded guest-memory inspection for this private frontend.
        // Raw bytes remain in its private working directory, never in stdout.
        if (FILE *request=std::fopen("debug-guest-read","r")) {
            unsigned long long tid=0;unsigned address=0,length=0;
            const bool parsed=std::fscanf(request,"%llu %x %u",&tid,&address,&length)==3;
            std::fclose(request);unlink("debug-guest-read");
            unlink("debug-guest-read.bin");
            bool valid=parsed && length>0 && length<=4096 && address<=0xffffffffU-length;
            std::vector<unsigned char> bytes;
            if(valid)for(auto &object:kernel_->get_thread_list()) {
                if(!object || object->unique_id()!=tid)continue;
                auto *thread=static_cast<eka2l1::kernel::thread *>(object.get());
                for(unsigned offset=0;offset<length;++offset) {
                    auto *source=eka2l1::ptr<unsigned char>(address+offset).get(thread->owning_process());
                    if(!source){valid=false;break;}bytes.push_back(*source);
                }
                break;
            }
            valid=valid && bytes.size()==length;
            if(valid)if(FILE *output=std::fopen("debug-guest-read.bin","wb")) {
                valid=std::fwrite(bytes.data(),1,bytes.size(),output)==bytes.size();std::fclose(output);
            } else valid=false;
            std::printf("guest_read thread=%llu address=%08x bytes=%u success=%d\n",tid,address,length,valid);
        }
        kernel_->get_ntimer()->debug_pending_events();
        std::printf("guest_ipc_sends=%zu\n",sends_);
        const auto begin=sends_>6?sends_-6:0;
        for(auto i=begin;i<sends_;++i) {auto &entry=recent_[i%recent_.size()];
            std::printf("recent_ipc thread=%llu server=%s opcode=%d request=%08x\n",entry.thread,entry.server,entry.opcode,entry.request);}
    }
};
