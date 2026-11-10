// Minimal standalone frontend services. Unsupported host UI is explicitly
// dismissed asynchronously; it never fabricates a user acceptance.
#include <drivers/ui/input_dialog.h>
#include <common/applauncher.h>
#include <atomic>
#include <cstdio>
#include <deque>
#include <memory>
#include <mutex>
namespace {
std::mutex queue_mutex;
std::deque<std::function<void()>> pending;
}
namespace n810_runtime {
void drain_frontend_callbacks() {
    std::deque<std::function<void()>> ready;
    {std::lock_guard<std::mutex> lock(queue_mutex);ready.swap(pending);}
    for (auto &callback:ready) callback();
}
}
namespace eka2l1::drivers::ui {
bool open_input_view(const std::u16string &,int,input_dialog_complete_callback) {
    std::fprintf(stderr,"frontend_input_view_unavailable\n");return false;
}
void close_input_view() {}
dialog_cancel_callback show_yes_no_dialog(const std::u16string &,const std::u16string &,const std::u16string &,yes_no_dialog_complete_callback complete) {
    std::fprintf(stderr,"frontend_modal_dialog_unavailable dismissal_queued=1\n");
    auto sent=std::make_shared<std::atomic<bool>>(false);
    auto dismiss=[sent,complete] {if (!sent->exchange(true) && complete) complete(-1);};
    {std::lock_guard<std::mutex> lock(queue_mutex);pending.push_back(dismiss);}
    // Cancellation is queued too: callbacks may acquire the emulated kernel lock.
    return [dismiss] {std::lock_guard<std::mutex> lock(queue_mutex);pending.push_back(dismiss);};
}
}
namespace eka2l1::common {
bool launch_browser(const std::string &) {std::fprintf(stderr,"frontend_browser_unavailable\n");return false;}
}
