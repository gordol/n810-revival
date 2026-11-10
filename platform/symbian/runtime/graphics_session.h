#include "runtime_debug.h"
#pragma once
#include "present_fb.h"
#include <drivers/graphics/graphics.h>
#include <drivers/itc.h>
#include <services/window/screen.h>
#include <atomic>
#include <cstdlib>
#include <poll.h>
#include <unistd.h>
#include <cstdio>
#include <future>
#include <functional>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <vector>
#include <chrono>
#include <cstring>
namespace n810_runtime {
extern std::function<void(const std::uint8_t *, unsigned, unsigned)> present_rgba;
const char *current_renderer();
}
class graphics_session {
    eka2l1::drivers::graphics_driver_ptr driver_;
    std::thread worker_;
    std::atomic<bool> failed_{false};
    std::mutex teardown_mutex_;
    std::condition_variable teardown_cv_;
    bool destroy_requested_ = false;
    std::unique_ptr<n810_framebuffer> framebuffer_;
    int present_status_ = 0;
    int grant_fd_ = -1;
    bool granted_ = false;
    bool visible_frame_saved_ = false;
    std::vector<std::uint8_t> readback_, flipped_readback_;
    bool compare_pending_ = false;
    unsigned compared_ = 0;
    int verified_orientation_ = 0;
    unsigned orientation_matches_ = 0;
    bool auto_rejected_ = false;
    double readback_ms_ = 0;
    bool async_present_ = false;
    std::atomic<unsigned long> queued_presentations_{0},completed_presentations_{0};
    static void complete_async_read(void *opaque,int result) noexcept {
        auto *self=static_cast<graphics_session *>(opaque);
        try {
            if(!result)throw std::runtime_error("Asynchronous screen read failed");
            // All reads and callbacks execute in FIFO order on the graphics
            // owner. This buffer is never read/written by the runtime thread.
            n810_runtime::present_rgba(self->readback_.data(),240,320);
            ++self->completed_presentations_;
        } catch(const std::exception &e) {
            std::fprintf(stderr,"graphics_failure=%s\n",e.what());self->failed_=true;
        } catch(...) {self->failed_=true;}
    }

public:
    std::atomic<unsigned long> frames{0}, displayed{0};
    explicit graphics_session(int inherited_fb) {
        async_present_=std::getenv("N810_SYMBIAN_ASYNC_PRESENT")!=nullptr;
        if(async_present_) {
            const char *orientation=std::getenv("N810_SYMBIAN_DIRECT_PRESENT");
            if(!orientation||std::strcmp(orientation,"top-down")||std::getenv("N810_SYMBIAN_PRESENT_COMPARE"))
                throw std::runtime_error("Async presentation requires verified top-down mode");
            readback_.resize(240U*320U*4U);
        }
        if (inherited_fb >= 0) {
            const char *grant=std::getenv("N810_SYMBIAN_DISPLAY_GRANT_FD");
            if (!grant) throw std::runtime_error("Display handoff descriptor required");
            grant_fd_=std::stoi(grant);
            framebuffer_=std::make_unique<n810_framebuffer>(inherited_fb);
        }
        n810_runtime::present_rgba=[this](const std::uint8_t *rgba,unsigned w,unsigned h) {
            auto number=++frames;
            if(compare_pending_) {
                unsigned changed=0,flipped=0;
                for(unsigned y=0;y<h;++y)for(unsigned x=0;x<w;++x) {
                    auto offset=4*(y*w+x),reverse=4*((h-1-y)*w+x);
                    changed+=std::memcmp(rgba+offset,readback_.data()+offset,3)!=0;
                    flipped+=std::memcmp(rgba+offset,readback_.data()+reverse,3)!=0;
                }
                std::printf("present_readback_compare frame=%lu changed_rgb_pixels=%u flipped_changed_rgb_pixels=%u readback_ms=%.3f\n",number,changed,flipped,readback_ms_);
                // Blank startup frames cannot establish vertical orientation.
                bool nonuniform=false;
                for(std::size_t p=1;p<static_cast<std::size_t>(w)*h && !nonuniform;++p)
                    nonuniform=std::memcmp(rgba+4*p,rgba,3)!=0;
                compare_pending_=false;
                if(nonuniform) {
                    ++compared_;
                    const int orientation=changed==0 && flipped!=0 ? 1 : flipped==0 && changed!=0 ? -1 : 0;
                    if(changed!=0 && flipped!=0) auto_rejected_=true;
                    if(orientation) {
                        if(verified_orientation_==orientation)++orientation_matches_;
                        else {verified_orientation_=orientation;orientation_matches_=1;}
                    }
                    if(orientation_matches_==3 && !auto_rejected_)
                        std::printf("present_direct_verified orientation=%s nonuniform_matches=3\n",verified_orientation_==1?"top-down":"bottom-up");
                }
            }
            if (number==1) {
                FILE *out=std::fopen("first-guest-frame.ppm","wb");
                if (out) {
                    std::fprintf(out,"P6\n%u %u\n255\n",w,h);
                    for (std::size_t p=0;p<static_cast<std::size_t>(w)*h;++p) std::fwrite(rgba+4*p,1,3,out);
                    std::fclose(out);
                }
            }
            bool varied=false;
            for (std::size_t p=1;p<static_cast<std::size_t>(w)*h && !varied;++p)
                varied=rgba[4*p]!=rgba[0] || rgba[4*p+1]!=rgba[1] || rgba[4*p+2]!=rgba[2];
            if (varied && !visible_frame_saved_) {
                FILE *out=std::fopen("first-visible-guest-frame.ppm","wb");
                if (out) {
                    std::fprintf(out,"P6\n%u %u\n255\n",w,h);
                    for (std::size_t p=0;p<static_cast<std::size_t>(w)*h;++p) std::fwrite(rgba+4*p,1,3,out);
                    std::fclose(out);visible_frame_saved_=true;
                }
            }
            if (framebuffer_ && (varied || granted_)) {
                if (!granted_) {
                    pollfd ready{grant_fd_,POLLIN,0};char grant=0;
                    if (poll(&ready,1,30000)<=0 || read(grant_fd_,&grant,1)!=1 || grant!='G')
                        throw std::runtime_error("Display ownership handoff failed");
                    granted_=true;
                }
                framebuffer_->present(rgba,w,h);auto shown=++displayed;
                if (shown==1) {FILE *done=std::fopen("visible-presentation-complete","w");if(done){std::fprintf(done,"1\n");std::fclose(done);}}
            }
            if (n810_runtime_debug() && (number==1 || number%30==0)) {
                std::printf("guest_frames=%lu display_updates=%lu renderer=%s\n",number,displayed.load(),n810_runtime::current_renderer());
                std::fflush(stdout);
            }
        };
        std::promise<void> ready;auto future=ready.get_future();
        worker_=std::thread([this,&ready] {
            bool initialized=false;
            try {
                eka2l1::drivers::window_system_info info;
                info.surface_width=240;info.surface_height=320;
                driver_=eka2l1::drivers::create_graphics_driver(eka2l1::drivers::graphic_api::opengl,info);
                if (!driver_) throw std::runtime_error("Graphics backend creation failed");
                driver_->set_display_hook([]{});
                initialized=true;ready.set_value();
                driver_->run();
            } catch (...) {
                try {throw;} catch (const std::exception &error) {std::fprintf(stderr,"graphics_failure=%s\n",error.what());}
                catch (...) {std::fprintf(stderr,"graphics_failure=unknown\n");}
                failed_=true;
                if(FILE *failure=std::fopen("graphics-failure","w")) {std::fputs("1\n",failure);std::fclose(failure);}
                if (driver_) driver_->abort();
                if (!initialized) {ready.set_exception(std::current_exception());driver_.reset();return;}
            }
            // GL resources must be destroyed on the thread with the current
            // OSMesa context, after the runtime has released its driver users.
            if(n810_runtime_debug()) std::fprintf(stderr,"runtime_teardown=graphics_run_stopped\n");
            std::unique_lock<std::mutex> lock(teardown_mutex_);
            teardown_cv_.wait(lock,[this]{return destroy_requested_;});
            if(n810_runtime_debug()) std::fprintf(stderr,"runtime_teardown=graphics_owner_destroy\n");
            driver_.reset();
            if(n810_runtime_debug()) std::fprintf(stderr,"runtime_teardown=graphics_owner_destroyed\n");
        });
        try {future.get();} catch (...) {worker_.join();n810_runtime::present_rgba={};throw;}
    }
    ~graphics_session() {
        if(n810_runtime_debug()) std::fprintf(stderr,"runtime_teardown=graphics_join\n");
        {
            std::lock_guard<std::mutex> lock(teardown_mutex_);
            if (driver_) driver_->abort();
            destroy_requested_=true;
        }
        teardown_cv_.notify_all();
        if (worker_.joinable()) worker_.join();
        n810_runtime::present_rgba={};
        if(n810_runtime_debug()) std::fprintf(stderr,"runtime_teardown=graphics_joined\n");
        if(async_present_)if(n810_runtime_debug()) std::fprintf(stderr,"async_present queued=%lu completed=%lu\n",queued_presentations_.load(),completed_presentations_.load());
    }
    auto *driver() {return driver_.get();}
    bool failed() const {return failed_;}
    void redraw(eka2l1::epoc::screen *screen) {
        using namespace eka2l1;
        if(async_present_) {
            if(driver_->aborted())return;
            const auto size=screen->current_mode().size;
            if(size.x!=240||size.y!=320)throw std::runtime_error("Unexpected asynchronous screen mode");
            drivers::command_list list(1);list.renew();list.size_=1;
            auto &cmd=*list.base_;cmd.opcode_=drivers::graphics_driver_read_bitmap;
            cmd.data_[0]=screen->screen_texture;
            cmd.data_[2]=(std::uint64_t(320)<<32)|240U;
            cmd.data_[3]=32;cmd.data_[4]=reinterpret_cast<std::uint64_t>(readback_.data());
            cmd.readback_completion_=&complete_async_read;cmd.readback_userdata_=this;
            ++queued_presentations_;
            driver_->submit_command_list(list);
            return;
        }
        driver_->wait_for(&present_status_);
        if (driver_->aborted()) return;
        drivers::graphics_command_builder builder;
        const auto size=screen->current_mode().size;
        // Preserve the N95 screen dimensions; no lower-resolution render target.
        if (size.x!=240 || size.y!=320) throw std::runtime_error("Unexpected N95 screen mode");
        const char *direct=std::getenv("N810_SYMBIAN_DIRECT_PRESENT");
        const bool auto_mode=direct && !std::strcmp(direct,"auto-verified");
        if(auto_mode) direct=!auto_rejected_ && orientation_matches_>=3 ?
            (verified_orientation_==1 ? "top-down":"bottom-up") : nullptr;
        const bool compare=(std::getenv("N810_SYMBIAN_PRESENT_COMPARE") && compared_<12) ||
            (auto_mode && !auto_rejected_ && !direct);
        if(direct || compare) {
            readback_.resize(static_cast<std::size_t>(size.x)*size.y*4);
            auto began=std::chrono::steady_clock::now();
            if(!drivers::read_bitmap(driver_.get(),screen->screen_texture,point(0,0),object_size(size),32,readback_.data()))
                throw std::runtime_error("Native presentation readback failed");
            readback_ms_=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-began).count();
            if(direct) {
                const std::uint8_t *pixels=readback_.data();
                if(!std::strcmp(direct,"bottom-up")) {
                    flipped_readback_.resize(readback_.size());
                    for(int y=0;y<size.y;++y)std::memcpy(flipped_readback_.data()+y*size.x*4,readback_.data()+(size.y-1-y)*size.x*4,size.x*4);
                    pixels=flipped_readback_.data();
                } else if(std::strcmp(direct,"top-down")) throw std::runtime_error("Unverified native presentation orientation");
                n810_runtime::present_rgba(pixels,size.x,size.y);
                return;
            }
            compare_pending_=true;
        }
        rect region;region.size=size;
        builder.set_swapchain_size(size);
        builder.backup_state();
        for (auto feature : {drivers::graphics_feature::cull,drivers::graphics_feature::depth_test,
             drivers::graphics_feature::blend,drivers::graphics_feature::stencil_test,drivers::graphics_feature::clipping})
            builder.set_feature(feature,false);
        builder.set_viewport(region);
        builder.draw_bitmap(screen->screen_texture,0,region,region,vec2(0,0),0.0f,0);
        builder.load_backup_state();
        present_status_=-100;builder.present(&present_status_);
        auto commands=builder.retrieve_command_list();driver_->submit_command_list(commands);
    }
};
