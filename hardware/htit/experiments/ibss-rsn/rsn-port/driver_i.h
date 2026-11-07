#pragma once
#include "wpa_supplicant_i.h"
int wpa_drv_send_mlme(struct wpa_supplicant*,const u8*,size_t,int,unsigned int,int);
int wpa_drv_tx_control_port(struct wpa_supplicant*,const u8*,u16,const u8*,size_t,int);
int wpa_drv_set_key(struct wpa_supplicant*,int,enum wpa_alg,const u8*,int,int,
                    const u8*,size_t,const u8*,size_t,enum key_flag);
int wpa_drv_sta_deauth(struct wpa_supplicant*,const u8*,u16);
int wpa_drv_sta_set_flags(struct wpa_supplicant*,const u8*,unsigned,unsigned,unsigned);
