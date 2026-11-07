// Scope receive-buffer allocations before Bluedroid copies controller input.
// Optional private diagnostics capture ACL packets only, never HCI events.
#if defined(HTIT_EXECUTOR) && (defined(HTIT_HCI_RX_TRACE) || defined(HTIT_BT_RX_INTERNAL))
#include <esp_bt.h>
#include <cstddef>
#ifdef HTIT_HCI_RX_TRACE
extern "C" void htit_executor_hci_trace(const uint8_t*, size_t);
#endif
#ifdef HTIT_BT_RX_INTERNAL
extern "C" void htit_bt_receive_scope(bool);
#endif
namespace {
esp_vhci_host_callback_t original{};
void available() {
    if (original.notify_host_send_available) original.notify_host_send_available();
}
int received(uint8_t* data, uint16_t length) {
#ifdef HTIT_HCI_RX_TRACE
    if (length >= 5 && data[0] == 2) htit_executor_hci_trace(data, length);
#endif
#ifdef HTIT_BT_RX_INTERNAL
    // Only the receive callback's buffers, never Bluetooth initialization.
    htit_bt_receive_scope(true);
#endif
    const int result = original.notify_host_recv ? original.notify_host_recv(data, length) : 0;
#ifdef HTIT_BT_RX_INTERNAL
    htit_bt_receive_scope(false);
#endif
    return result;
}
const esp_vhci_host_callback_t capture{available, received};
}
extern "C" esp_err_t __real_esp_vhci_host_register_callback(const esp_vhci_host_callback_t*);
extern "C" esp_err_t __wrap_esp_vhci_host_register_callback(const esp_vhci_host_callback_t* callbacks) {
    if (!callbacks) return __real_esp_vhci_host_register_callback(callbacks);
    original = *callbacks;
    return __real_esp_vhci_host_register_callback(&capture);
}
#endif
