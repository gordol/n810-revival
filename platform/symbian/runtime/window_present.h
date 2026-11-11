#pragma once
// Private frame transport: publish GPU identities and retain them until Pocket
// forgets its imports. No application pixels pass through this socket.
#include <array>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>
#include <sys/socket.h>
#include <poll.h>
#include <fcntl.h>
#include <unistd.h>
namespace n810_runtime {
inline int window_cancel_write=-1;
void interrupt_window() noexcept {if(window_cancel_write>=0){const char c='C';auto ignored=write(window_cancel_write,&c,1);(void)ignored;}}
enum window_kind {window_begin=1,window_ready,window_frame,window_ack,window_close,window_pause,window_resume,window_error};
struct window_image {std::uint32_t version,width,height,format,session,generation,slot,reserved;};
struct window_header {char magic[4];std::uint32_t kind;std::uint64_t serial;std::uint32_t width,height,count,reserved;};
struct window_part {std::uint32_t x,y,w,h;window_image image;};
static_assert(sizeof(window_header)==32&&sizeof(window_part)==48,"Symbian window wire ABI");
class window_presenter {
    int fd_=-1,cancel_[2]={-1,-1};
    GLuint texture_=0;
    bool update_open_=false,retired_=false,presented_=false;
    std::uint64_t serial_=0;
    window_image published_{};
    bool pinned_=false;
    int (*publish_)(unsigned,window_image *)=nullptr;
    int (*release_)(unsigned,const window_image *)=nullptr;
    void send(unsigned kind,const window_part *part=nullptr) {
        struct {window_header h;window_part p;} msg{};
        std::memcpy(msg.h.magic,"SWN1",4);msg.h.kind=kind;msg.h.serial=serial_;
        if(part){msg.h.width=240;msg.h.height=320;msg.h.count=1;msg.p=*part;}
        const auto size=sizeof(window_header)+(part?sizeof(window_part):0);
        if(::send(fd_,&msg,size,MSG_NOSIGNAL)!=static_cast<ssize_t>(size))throw std::runtime_error("Pocket window connection closed");
    }
    unsigned receive() {
        pollfd fds[2]={{fd_,POLLIN,0},{cancel_[0],POLLIN,0}};
        int result;do{result=poll(fds,2,-1);}while(result<0&&errno==EINTR);
        if(result<=0||fds[1].revents)throw std::runtime_error("Pocket window interrupted");
        window_header h{};iovec iov{&h,sizeof(h)};msghdr msg{};msg.msg_iov=&iov;msg.msg_iovlen=1;
        const auto n=recvmsg(fd_,&msg,0);
        if(n!=static_cast<ssize_t>(sizeof(h))||(msg.msg_flags&MSG_TRUNC)||std::memcmp(h.magic,"SWN1",4)||(h.serial!=serial_&&!(h.serial==0&&(h.kind==window_pause||h.kind==window_resume)))||h.width||h.height||h.count||h.reserved)
            throw std::runtime_error("Invalid Pocket window acknowledgement");
        return h.kind;
    }
    void wait(unsigned expected) {
        while(true){
            const auto kind=receive();
            if(kind==expected)return;
            if(kind==window_pause){
                glFinish();send(window_pause);
                bool expected_seen=false;
                while(true){const auto paused_kind=receive();if(paused_kind==window_resume)break;
                    if(paused_kind==expected&&!expected_seen){expected_seen=true;continue;}
                    throw std::runtime_error("Invalid Pocket window resume");}
                if(expected_seen)return;
            }else if(kind==window_resume){continue;}
            else throw std::runtime_error("Unexpected Pocket window acknowledgement");
        }
    }
    bool retire() noexcept {
        window_header request{};std::memcpy(request.magic,"SWN1",4);request.kind=window_close;request.serial=serial_;
        const auto ignored=::send(fd_,&request,sizeof(request),MSG_NOSIGNAL);(void)ignored;
        const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(5);
        while(std::chrono::steady_clock::now()<deadline){
            const auto left=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-std::chrono::steady_clock::now()).count();
            pollfd peer{fd_,POLLIN,0};const int ready=poll(&peer,1,static_cast<int>(left));
            if(ready<0&&errno==EINTR)continue;
            if(ready<=0)return false;
            window_header response{};iovec buffer{&response,sizeof(response)};msghdr message{};message.msg_iov=&buffer;message.msg_iovlen=1;
            const auto n=recvmsg(fd_,&message,MSG_DONTWAIT);
            if(message.msg_flags&MSG_TRUNC)return false;
            if(!n)return true; // Trusted consumer closes only after forgetting imports.
            // Cancellation may win poll while the completed frame ACK is queued.
            // It confirms frame consumption, not import retirement: drain it and
            // still require the subsequent CLOSE/READY handshake before release.
            if(n==static_cast<ssize_t>(sizeof(response))&&!std::memcmp(response.magic,"SWN1",4)&&response.kind==window_ack&&response.serial==serial_&&!response.width&&!response.height&&!response.count&&!response.reserved)continue;
            if(n==static_cast<ssize_t>(sizeof(response))&&!std::memcmp(response.magic,"SWN1",4)&&response.kind==window_ready&&response.serial==serial_&&!response.width&&!response.height&&!response.count&&!response.reserved)return true;
            if(n==static_cast<ssize_t>(sizeof(response))&&!std::memcmp(response.magic,"SWN1",4)&&(response.kind==window_pause||response.kind==window_resume)&&!response.serial&&!response.width&&!response.height&&!response.count&&!response.reserved)continue;
            if(n<0&&(errno==EAGAIN||errno==EINTR))continue;
            return false;
        }
        return false;
    }
public:
    explicit window_presenter(int fd):fd_(fd) {
        publish_=reinterpret_cast<int(*)(unsigned,window_image *)>(dlsym(RTLD_DEFAULT,"n810_mbx_window_export"));
        release_=reinterpret_cast<int(*)(unsigned,const window_image *)>(dlsym(RTLD_DEFAULT,"n810_mbx_window_export_release"));
        if(!publish_||!release_)throw std::runtime_error("Native retained GPU window API missing");
        if(pipe2(cancel_,O_CLOEXEC|O_NONBLOCK))throw std::runtime_error("Window cancellation pipe failed");
        window_cancel_write=cancel_[1];
    }
    void finish() noexcept {
        if(retired_)return;
        glFinish();
        if(!retire()||(pinned_&&release_(texture_,&published_))){
            std::fprintf(stderr,"window_retirement_failed=consumer_or_gpu_ack\n");std::abort();
        }
        pinned_=false;retired_=true;
    }
    ~window_presenter(){
        finish();window_cancel_write=-1;
        // Keep this pair valid until process exit: a concurrent signal handler
        // may already have loaded the write fd. It must never hit a reused fd.
    }
    void begin_update(){
        glFinish();++serial_;send(window_begin);wait(window_ready);
        if(pinned_){if(release_(texture_,&published_))throw std::runtime_error("Retained window release failed");pinned_=false;}
        update_open_=true;
    }
    void before_write(unsigned texture){if(pinned_&&texture==texture_)begin_update();}
    void before_draw(unsigned hint){
        if(!pinned_||hint!=texture_)return;
        GLint fbo=0,type=0,name=0;glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&fbo);
        if(!fbo)return;
        glGetFramebufferAttachmentParameteriv(GL_DRAW_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_FRAMEBUFFER_ATTACHMENT_OBJECT_TYPE,&type);
        if(type!=GL_TEXTURE)return;
        glGetFramebufferAttachmentParameteriv(GL_DRAW_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_FRAMEBUFFER_ATTACHMENT_OBJECT_NAME,&name);
        if(static_cast<unsigned>(name)==texture_)begin_update();
    }
    bool present(unsigned source,unsigned width,unsigned height){
        if(width!=240||height!=320)throw std::runtime_error("Unexpected Symbian window dimensions");
        if(!presented_){
            glFinish();const int result=publish_(source,&published_);
            // WSERV can announce a clear-only startup frame before any native
            // image exists. Keep Pocket responsive until the first GPU draw.
            if(result==-ENODATA)return false;
            if(result)throw std::runtime_error("First native GPU image publication failed");
            texture_=source;pinned_=true;++serial_;send(window_begin);wait(window_ready);
        }else{
            if(!update_open_)begin_update();else glFinish();
            if(publish_(source,&published_))throw std::runtime_error("Native-size GPU window publication failed");
            texture_=source;pinned_=true;
        }
        // Publish WSERV's completed native target directly. No snapshot blit,
        // CPU readback, pixel upload, or second native-size allocation.
        update_open_=false;presented_=true;
        window_part part{0,0,240,320,published_};send(window_frame,&part);wait(window_ack);return true;
    }
};
}
