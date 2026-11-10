// N810 framebuffer output through an explicitly inherited descriptor only.
// The supervisor retains desktop ownership and restores its saved pixels.
#pragma once
#include <cstddef>
#include <linux/fb.h>
#include <linux/omapfb.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <cstdint>
#include <stdexcept>
#include <cerrno>
#include <cstring>
#include <string>

class n810_framebuffer {
    int fd_;
    std::uint16_t *pixels_ = nullptr;
public:
    explicit n810_framebuffer(int fd) : fd_(fd) {
        fb_var_screeninfo v{}; fb_fix_screeninfo f{};
        if (ioctl(fd_, FBIOGET_VSCREENINFO, &v) || ioctl(fd_, FBIOGET_FSCREENINFO, &f) ||
            v.xres != 800 || v.yres != 480 || v.xoffset || v.yoffset || v.bits_per_pixel != 16 ||
            v.red.offset != 11 || v.red.length != 5 || v.green.offset != 5 || v.green.length != 6 ||
            v.blue.offset || v.blue.length != 5 || v.transp.length ||
            v.red.msb_right || v.green.msb_right || v.blue.msb_right || f.line_length != 1600 || f.smem_len < 768000)
            throw std::runtime_error("Unexpected N810 framebuffer format");
        void *map = mmap(nullptr, 768000, PROT_READ | PROT_WRITE, MAP_SHARED, fd_, 0);
        if (map == MAP_FAILED) throw std::runtime_error("N810 framebuffer map failed");
        pixels_ = static_cast<std::uint16_t *>(map);
    }
    ~n810_framebuffer() { if (pixels_) munmap(pixels_, 768000); }
    n810_framebuffer(const n810_framebuffer &) = delete;
    void present(const std::uint8_t *rgba, unsigned width, unsigned height) {
        if (!width || !height || width > 800 || height > 480)
            throw std::runtime_error("Guest display does not fit N810");
        if (ioctl(fd_, OMAPFB_SYNC_GFX)) throw std::runtime_error("Display synchronization failed");
        const unsigned left=(800-width)/2, top=(480-height)/2;
        for (unsigned y=0;y<height;++y) for (unsigned x=0;x<width;++x) {
            const auto *p=rgba+4*(y*width+x);
            pixels_[(y+top)*800+x+left]=((p[0]>>3)<<11)|((p[1]>>2)<<5)|(p[2]>>3);
        }
        omapfb_update_window update{};
        // Use the already verified full-panel transfer on this kernel. The
        // guest remains centered at its native resolution; only bus coverage
        // changes. The partial-window ioctl was rejected on the physical N810.
        update.width=800; update.height=480;
        update.out_width=800; update.out_height=480;
        update.format=OMAPFB_COLOR_RGB565;
        if (ioctl(fd_, OMAPFB_UPDATE_WINDOW, &update))
            throw std::runtime_error(std::string("Display update failed: ")+std::strerror(errno));
        if (ioctl(fd_, OMAPFB_SYNC_GFX)) throw std::runtime_error("Display completion failed");
    }
};
