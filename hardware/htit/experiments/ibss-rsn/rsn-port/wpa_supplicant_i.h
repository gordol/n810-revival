#pragma once
// Deliberately small platform context for the unchanged upstream ibss_rsn.c.
#include "common/defs.h"
#include "drivers/driver.h"
struct wpa_ssid { unsigned group_rekey; };
struct wpa_supplicant {
    u8 own_addr[6],bssid[6];
    u64 drv_flags;
    void* l2;
    void* port;
    struct wpa_ssid ssid;
};
static inline struct wpa_ssid* wpa_supplicant_get_ssid(struct wpa_supplicant* s) {return &s->ssid;}
