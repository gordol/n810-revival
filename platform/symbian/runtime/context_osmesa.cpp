#include "runtime_debug.h"
// Private N810 compatibility renderer. Does not open a GPU device or replace Mesa.
// Linked instead of upstream context.cpp in the standalone runtime executable.
#include <drivers/graphics/context.h>
#define GL_GLEXT_PROTOTYPES
#include <GL/osmesa.h>
#include "window_present.h"
#include <cstdint>
#include <functional>
#include <stdexcept>
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <atomic>

namespace n810_runtime {
// The frontend owns display access and restoration; this adapter only supplies pixels.
std::function<void(const std::uint8_t *, unsigned, unsigned)> present_rgba;
static std::atomic<unsigned> gpu_contexts_verified{0};
static window_presenter *window_owner=nullptr;
void retire_window(){if(window_owner)window_owner->finish();}
void prepare_window_draw(unsigned hint){if(window_owner)window_owner->before_draw(hint);}
void prepare_window_write(unsigned texture){if(window_owner)window_owner->before_write(texture);}
bool present_window(unsigned texture,unsigned width,unsigned height){if(!window_owner)throw std::runtime_error("Retained GPU window owner missing");return window_owner->present(texture,width,height);}
const char *current_renderer() {
    const auto *name = reinterpret_cast<const char *>(glGetString(GL_RENDERER));
    return name ? name : gpu_contexts_verified.load() ? "Nokia MBX GPU transform, lighting and rasterizer (verified graphics thread)" : "no verified graphics context";
}
}
namespace eka2l1::drivers::graphics {
class n810_osmesa_context final : public gl_context {
    OSMesaContext context_ = nullptr;
    bool verified_ = false;
    std::unique_ptr<n810_runtime::window_presenter> window_;
    std::vector<std::uint8_t> rgba_;
public:
    n810_osmesa_context(unsigned width, unsigned height, OSMesaContext shared = nullptr) {
        const char *requested = std::getenv("N810_SYMBIAN_FIXED_FUNCTION");
        if (!requested || std::strcmp(requested, "gpu"))
            throw std::runtime_error("Symbian graphics requires MBX GPU mode; software rendering is disabled");
        const int attributes[] = {OSMESA_FORMAT, OSMESA_RGBA, OSMESA_DEPTH_BITS, 24,
            OSMESA_STENCIL_BITS, 8, OSMESA_PROFILE, OSMESA_COMPAT_PROFILE,
            OSMESA_CONTEXT_MAJOR_VERSION, 3, OSMESA_CONTEXT_MINOR_VERSION, 3, 0};
        if(n810_runtime_debug()) std::fprintf(stderr,"graphics_phase=osmesa_create\n");
        context_ = OSMesaCreateContextAttribs(attributes, shared);
        if(n810_runtime_debug()) std::fprintf(stderr,"graphics_phase=osmesa_created\n");
        if (!context_) throw std::runtime_error("N810 private GPU context creation failed");
        m_opengl_mode = mode::opengl;
        m_is_shared = shared != nullptr;
        try {
        update(width, height);
        const char *renderer=reinterpret_cast<const char *>(glGetString(GL_RENDERER));
        if(!renderer || std::strcmp(renderer,"Nokia MBX GPU transform, lighting and rasterizer"))
            throw std::runtime_error("GPU mode requires the verified MBX renderer; no software fallback");
        if(!m_is_shared)if(const char *fd=std::getenv("N810_SYMBIAN_WINDOW_FD")) {
            window_=std::make_unique<n810_runtime::window_presenter>(std::stoi(fd));n810_runtime::window_owner=window_.get();
        }
        verified_=true;n810_runtime::gpu_contexts_verified.fetch_add(1);
        if(n810_runtime_debug()) std::fprintf(stderr,"graphics_fixed_function=gpu renderer=%s\n",renderer);
        if(n810_runtime_debug()) std::fprintf(stderr,"graphics_phase=osmesa_bound\n");
        } catch (...) {
            OSMesaDestroyContext(context_);
            context_ = nullptr;
            throw;
        }
    }
    ~n810_osmesa_context() override {
        if(n810_runtime_debug()) std::fprintf(stderr,"graphics_destroy=osmesa_context\n");
        if(window_){n810_runtime::window_owner=nullptr;window_.reset();}
        if(verified_)n810_runtime::gpu_contexts_verified.fetch_sub(1);
        OSMesaDestroyContext(context_);
        if(n810_runtime_debug()) std::fprintf(stderr,"graphics_destroy=osmesa_context_done\n");
    }
    bool make_current() override {
        const bool ok = OSMesaMakeCurrent(context_, rgba_.data(), GL_UNSIGNED_BYTE,
            m_backbuffer_width, m_backbuffer_height);
        if (ok) OSMesaPixelStore(OSMESA_Y_UP, 0);
        return ok;
    }
    bool clear_current() override { return OSMesaMakeCurrent(nullptr, nullptr, GL_UNSIGNED_BYTE, 0, 0); }
    void swap_buffers() override {
        glFinish();
        if (!m_is_shared && !window_ && n810_runtime::present_rgba)
            n810_runtime::present_rgba(rgba_.data(), m_backbuffer_width, m_backbuffer_height);
    }
    void update(unsigned width, unsigned height) override {
        if (!width || !height || width > 800 || height > 480)
            throw std::runtime_error("N810 surface exceeds bounded display dimensions");
        m_backbuffer_width = width;
        m_backbuffer_height = height;
        rgba_.resize(static_cast<std::size_t>(width) * height * 4);
        if (!make_current()) throw std::runtime_error("N810 GPU readback surface binding failed");
    }
    void set_swap_interval(std::int32_t) override {}
    bool is_headless() const override { return false; }
    std::unique_ptr<gl_context> create_shared_context() override {
        return std::make_unique<n810_osmesa_context>(m_backbuffer_width, m_backbuffer_height, context_);
    }
};
std::unique_ptr<gl_context> make_gl_context(const drivers::window_system_info &info, bool, bool) {
    return std::make_unique<n810_osmesa_context>(info.surface_width, info.surface_height);
}
}
