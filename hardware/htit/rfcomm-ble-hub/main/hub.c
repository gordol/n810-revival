/* Pocket HTIT-TB hub. Callbacks copy events; one worker owns all session state. */
#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_bt.h"
#include "esp_bt_device.h"
#include "esp_bt_main.h"
#include "esp_gap_ble_api.h"
#include "esp_gap_bt_api.h"
#include "esp_gatt_common_api.h"
#include "esp_gattc_api.h"
#include "esp_heap_caps.h"
#include "esp_spp_api.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "wire.h"
#include "lora.h"
#include <stdio.h>
#include <string.h>

#define HOSTS 3 /* USB=0, two authenticated SPP sessions=1,2 */
#define OUT_DEPTH 512
#define LEASE_US 30000000LL
#define NAME "Pocket-HTIT-Hub"
enum {
    E_USB,
    E_SPP_UP,
    E_SPP_DOWN,
    E_SPP_RX,
    E_SPP_SENT,
    E_SPP_CONG,
    E_SPP_INIT,
    E_PIN,
    E_REG,
    E_SCAN_PARAM,
    E_SCAN,
    E_SCAN_DONE,
    E_SCAN_STOP,
    E_OPEN,
    E_MTU,
    E_SERVICE,
    E_SEARCH_DONE,
    E_NOTIFY_REG,
    E_DESC_WRITTEN,
    E_BLE_RX,
    E_BLE_WRITTEN,
    E_BLE_DOWN,
    E_PASSKEY,
    E_SECURITY,
    E_AUTH
};
typedef struct {
    int type, a, b, c;
    uint32_t handle;
    uint16_t len;
    uint8_t data[HUB_PAYLOAD];
} event;
typedef struct {
    uint16_t len, sent;
    uint8_t bytes[HUB_ENCODED];
} output;
typedef struct {
    uint32_t handle;
    bool online, busy, congested;
    hub_parser parser;
    output *out;
    unsigned head, count;
} host;
static QueueHandle_t events;
static host hosts[HOSTS];
static unsigned overflow;
static int owner = -1;
static int lora_owner = -1;
static int64_t lora_lease, lora_activity_until;
static uint16_t lora_request;
static lora_config lora_profile;
static int64_t lease_until, pair_until;
static uint8_t pair_pin[16];
static uint8_t pair_pin_len;
static esp_gatt_if_t gif = ESP_GATT_IF_NONE;
static uint16_t conn, mtu = 23, svc_start, svc_end, rx_handle, tx_handle, cccd;
static bool connecting, connected, ready, scanning, scan_ready, connect_after_scan;
static bool ble_pending, passkey_pending, secured;
static uint16_t pending_id;
static uint8_t target[6], target_type;
static int64_t ble_deadline;
/* HTIT-WB V0.2 schematic: active-high yellow=23, blue=25, green=22.
 * Yellow is our heartbeat; green stays reserved for the onboard LoRa service. */
static int64_t activity_until;
static void payload_activity(void) {
    int64_t t = esp_timer_get_time();
    /* Continuous traffic must flicker, not hold the connected indicator dark. */
    if (t >= activity_until + 170000)
        activity_until = t + 80000;
}
static void update_leds(void) {
    int64_t t = esp_timer_get_time();
    bool classic = hosts[1].online || hosts[2].online;
    bool pairing = t < pair_until || connecting || (connected && !ready);
    bool blue = ready ? t >= activity_until :
                pairing ? (t % 250000 < 125000) :
                classic ? (t % 2000000 < 1000000) : false;
    gpio_set_level(GPIO_NUM_23, t % 2000000 < 80000);
    gpio_set_level(GPIO_NUM_25, blue);
    gpio_set_level(GPIO_NUM_22, lora_online() && (lora_busy() || t < lora_activity_until || t % 2000000 < 50000));
}
static const uint8_t service_uuid[16] = {0x9e, 0xca, 0xdc, 0x24, 0x0e, 0xe5, 0xa9, 0xe0,
                                         0x93, 0xf3, 0xa3, 0xb5, 0x01, 0x00, 0x40, 0x6e};
static int64_t now(void) { return esp_timer_get_time(); }
static void post(event *e) {
    if (xQueueSend(events, e, 0) != pdTRUE)
        __atomic_store_n(&overflow, 1, __ATOMIC_RELAXED);
}
static void simple(int type, int a, int b) {
    event e = {.type = type, .a = a, .b = b};
    post(&e);
}
static int slot(uint32_t h) {
    for (int i = 1; i < HOSTS; i++)
        if (hosts[i].online && hosts[i].handle == h)
            return i;
    return -1;
}
static void disconnect_ble(void);
static void lose_owner(void) {
    owner = -1;
    lease_until = 0;
    disconnect_ble();
}
static void drop_host(int i) {
    if(i==lora_owner){lora_enable(false);lora_owner=-1;lora_request=0;}
    if (i == owner)
        lose_owner();
    if (i > 0 && hosts[i].online)
        esp_spp_disconnect(hosts[i].handle);
    output *storage = hosts[i].out;
    memset(&hosts[i], 0, sizeof(hosts[i]));
    hosts[i].out = storage;
    hosts[0].online = true;
}
static bool send_frame(int i, const hub_frame *f) {
    if (i < 0 || i >= HOSTS || !hosts[i].online)
        return false;
    host *h = &hosts[i];
    if (h->count == OUT_DEPTH) {
        drop_host(i);
        return false;
    }
    output *o = &h->out[(h->head + h->count) % OUT_DEPTH];
    o->sent = 0;
    o->len = hub_encode(f, o->bytes, sizeof(o->bytes));
    if (!o->len)
        return false;
    h->count++;
    return true;
}
static void reply(int i, const hub_frame *req, uint8_t status, const void *data, size_t len) {
    hub_frame r = {
        .service = req->service, .op = (uint8_t)(req->op | 0x80), .id = req->id, .len = len + 1};
    if (len > HUB_PAYLOAD - 1)
        return;
    r.data[0] = status;
    if (len)
        memcpy(r.data + 1, data, len);
    send_frame(i, &r);
}
static void notice(uint8_t op, const char *text) {
    if (owner < 0)
        return;
    hub_frame f = {.service = 0, .op = op, .len = strlen(text)};
    memcpy(f.data, text, f.len);
    send_frame(owner, &f);
}
static void pump(void) {
    for (int i = 0; i < HOSTS; i++) {
        host *h = &hosts[i];
        if (!h->online || !h->count || h->busy || h->congested)
            continue;
        output *o = &h->out[h->head];
        if (i == 0) {
            /* Never wait for a slow USB host while BLE notifications arrive. */
            int written =
                uart_tx_chars(UART_NUM_0, (const char *)o->bytes + o->sent, o->len - o->sent);
            if (written > 0)
                o->sent += written;
            if (o->sent == o->len) {
                h->head = (h->head + 1) % OUT_DEPTH;
                h->count--;
            }
        } else {
            h->busy = true;
            if (esp_spp_write(h->handle, o->len, o->bytes) != ESP_OK)
                drop_host(i);
        }
    }
}
static void disconnect_ble(void) {
    ready = false;
    ble_pending = false;
    passkey_pending = false;
    connect_after_scan = false;
    if (scanning)
        esp_ble_gap_stop_scanning();
    /* Keep connecting/connected until CLOSE/DISCONNECT so old events cannot
       be mistaken for a newly claimed session. */
    if (connected)
        esp_ble_gattc_close(gif, conn);
    else if (connecting)
        esp_ble_gap_disconnect(target);
}
static bool owned(int i) { return i == owner && now() < lease_until; }
static bool begin_connect(void) {
    svc_start = svc_end = rx_handle = tx_handle = cccd = 0;
    mtu = 23;
    secured = false;
    connecting = true;
    ble_deadline = now() + 15000000;
    if (esp_ble_gattc_open(gif, target, target_type, true) != ESP_OK) {
        connecting = false;
        return false;
    }
    return true;
}
static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void lora_received(const uint8_t *data,size_t n,int16_t rssi,int8_t snr) {
    if(lora_owner<0||n>508)return;
    hub_frame f={.service=3,.op=0x90,.len=n+3};
    f.data[0]=rssi;f.data[1]=rssi>>8;f.data[2]=snr;memcpy(f.data+3,data,n);
    lora_activity_until=now()+100000;send_frame(lora_owner,&f);
}
static void lora_completed(bool success) {
    if(lora_owner>=0){hub_frame f={.service=3,.op=4,.id=lora_request};reply(lora_owner,&f,success?0:4,NULL,0);}
    lora_request=0;lora_activity_until=now()+100000;
}
static void local_lora(int i,const hub_frame *f) {
    bool mine=i==lora_owner&&now()<lora_lease;
    if(mine)lora_lease=now()+LEASE_US;
    if(f->op==1&&f->len==0){
        if(lora_owner>=0&&!mine){reply(i,f,2,NULL,0);return;}
        lora_owner=i;lora_lease=now()+LEASE_US;reply(i,f,0,NULL,0);return;
    }
    if(f->op==5&&f->len==0){
        uint8_t data[14]={(uint8_t)(lora_owner<0?255:lora_owner),lora_online(),lora_busy()};
        uint32_t freq=lora_profile.frequency,bw=lora_profile.bandwidth;
        for(int j=0;j<4;j++){data[3+j]=freq>>(8*j);data[7+j]=bw>>(8*j);}
        data[11]=lora_profile.sf;data[12]=lora_profile.cr;data[13]=lora_profile.power;
        reply(i,f,0,data,sizeof(data));return;
    }
    if(!mine){reply(i,f,3,NULL,0);return;}
    if(f->op==2&&f->len==11){
        lora_config c={.frequency=le32(f->data),.bandwidth=le32(f->data+4),.sf=f->data[8],.cr=f->data[9],.power=f->data[10]};
        bool ok=lora_configure(&c);if(ok)lora_profile=c;reply(i,f,ok?0:1,NULL,0);
    }else if(f->op==3&&f->len==1&&f->data[0]<=1){
        if(lora_busy()){reply(i,f,2,NULL,0);return;}
        bool ok=lora_enable(f->data[0]);reply(i,f,ok?0:2,NULL,0);
    }else if(f->op==4&&f->len>0&&f->len<=508){
        if(lora_send(f->data,f->len))lora_request=f->id;else reply(i,f,2,NULL,0);
    }else if(f->op==6&&f->len==0){
        lora_enable(false);lora_owner=-1;lora_request=0;reply(i,f,0,NULL,0);
    }else reply(i,f,1,NULL,0);
}
static void frame_in(const hub_frame *f, void *context) {
    int i = (int)(intptr_t)context;
    if (f->op & 0x80)
        return;
    if (owned(i))
        lease_until = now() + LEASE_US;
    if (f->service == 0) {
        switch (f->op) {
        case 1: { /* Hello: binary identity and capabilities; no automatic radio use. */
            uint8_t data[] = {1, (uint8_t)i, 0x0f};
            reply(i, f, 0, data, sizeof(data));
            break;
        }
        case 2: {
            uint8_t data[] = {(uint8_t)(owner < 0 ? 255 : owner),
                              ready,
                              connected,
                              scanning,
                              (uint8_t)mtu,
                              (uint8_t)(mtu >> 8),
                              hosts[1].online,
                              hosts[2].online};
            reply(i, f, 0, data, sizeof(data));
            break;
        }
        case 7: /* Claim / renew. No takeover of a live session. */
            if ((owner >= 0 && !owned(i)) || (owner < 0 && (connected || connecting)))
                reply(i, f, 2, NULL, 0);
            else {
                owner = i;
                lease_until = now() + LEASE_US;
                reply(i, f, 0, NULL, 0);
            }
            break;
        case 8:
            if (!owned(i))
                reply(i, f, 3, NULL, 0);
            else {
                lose_owner();
                reply(i, f, 0, NULL, 0);
            }
            break;
        case 9: /* Open legacy pairing window, USB only. PIN never returned/logged. */
            if (i != 0 || f->len < 4 || f->len > 16) {
                reply(i, f, 3, NULL, 0);
                break;
            }
            for (int j = 0; j < f->len; j++)
                if (f->data[j] < '0' || f->data[j] > '9') {
                    reply(i, f, 1, NULL, 0);
                    return;
                }
            memcpy(pair_pin, f->data, f->len);
            pair_pin_len = f->len;
            pair_until = now() + 120000000;
            esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
            reply(i, f, 0, NULL, 0);
            break;
        case 3:
            if (!owned(i))
                reply(i, f, 3, NULL, 0);
            else if (!scan_ready || scanning || connecting || connected)
                reply(i, f, 2, NULL, 0);
            else {
                scanning = true;
                if (esp_ble_gap_start_scanning(5) != ESP_OK) {
                    scanning = false;
                    reply(i, f, 4, NULL, 0);
                } else
                    reply(i, f, 0, NULL, 0);
            }
            break;
        case 4:
            if (!owned(i))
                reply(i, f, 3, NULL, 0);
            else if (f->len != 7 || f->data[0] > 1)
                reply(i, f, 1, NULL, 0);
            else if (gif == ESP_GATT_IF_NONE || connecting || connected || connect_after_scan)
                reply(i, f, 2, NULL, 0);
            else {
                target_type = f->data[0];
                memcpy(target, f->data + 1, 6);
                if (scanning) {
                    connect_after_scan = true;
                    esp_ble_gap_stop_scanning();
                    reply(i, f, 0, NULL, 0);
                } else
                    reply(i, f, begin_connect() ? 0 : 4, NULL, 0);
            }
            break;
        case 5:
            if (!owned(i))
                reply(i, f, 3, NULL, 0);
            else {
                disconnect_ble();
                reply(i, f, 0, NULL, 0);
            }
            break;
        case 6:
            if (!owned(i) || !passkey_pending || f->len != 6) {
                reply(i, f, 3, NULL, 0);
                break;
            }
            {
                uint32_t pin = 0;
                for (int j = 0; j < 6; j++) {
                    if (f->data[j] < '0' || f->data[j] > '9') {
                        reply(i, f, 1, NULL, 0);
                        return;
                    }
                    pin = pin * 10 + f->data[j] - '0';
                }
                esp_ble_passkey_reply(target, true, pin);
                passkey_pending = false;
                reply(i, f, 0, NULL, 0);
            }
            break;
        default:
            reply(i, f, 5, NULL, 0);
        }
    } else if (f->service == 1 && f->op == 1) {
        if (!owned(i))
            reply(i, f, 3, NULL, 0);
        else if (!ready || ble_pending)
            reply(i, f, 2, NULL, 0);
        else if (!f->len || f->len > mtu - 3)
            reply(i, f, 6, NULL, 0);
        else {
            payload_activity();
            pending_id = f->id;
            ble_pending = true;
            ble_deadline = now() + 10000000;
            if (esp_ble_gattc_write_char(gif, conn, rx_handle, f->len, (uint8_t *)f->data,
                                         ESP_GATT_WRITE_TYPE_RSP,
                                         ESP_GATT_AUTH_REQ_NONE) != ESP_OK) {
                ble_pending = false;
                reply(i, f, 4, NULL, 0);
            }
        }
    } else if (f->service == 2 && f->op == 1) {
        if (f->len < 1 || f->data[0] >= HOSTS || f->data[0] == i || !hosts[f->data[0]].online)
            reply(i, f, 1, NULL, 0);
        else {
            payload_activity();
            hub_frame r = *f;
            r.op = 0x90;
            r.data[0] = i;
            bool ok = send_frame(f->data[0], &r);
            reply(i, f, ok ? 0 : 4, NULL, 0);
        }
    } else if(f->service==3)
        local_lora(i,f);
    else reply(i, f, 5, NULL, 0);
}
static void spp_cb(esp_spp_cb_event_t t, esp_spp_cb_param_t *p) {
    event e = {0};
    switch (t) {
    case ESP_SPP_INIT_EVT:
        simple(E_SPP_INIT, p->init.status, 0);
        return;
    case ESP_SPP_SRV_OPEN_EVT:
        e.type = E_SPP_UP;
        e.handle = p->srv_open.handle;
        e.a = p->srv_open.status;
        break;
    case ESP_SPP_CLOSE_EVT:
        e.type = E_SPP_DOWN;
        e.handle = p->close.handle;
        break;
    case ESP_SPP_DATA_IND_EVT:
        for (size_t off = 0; off < p->data_ind.len;) {
            e.type = E_SPP_RX;
            e.handle = p->data_ind.handle;
            e.len = p->data_ind.len - off;
            if (e.len > HUB_PAYLOAD)
                e.len = HUB_PAYLOAD;
            memcpy(e.data, p->data_ind.data + off, e.len);
            post(&e);
            off += e.len;
        }
        return;
    case ESP_SPP_WRITE_EVT:
        e.type = E_SPP_SENT;
        e.handle = p->write.handle;
        e.a = p->write.status;
        e.b = p->write.cong;
        break;
    case ESP_SPP_CONG_EVT:
        e.type = E_SPP_CONG;
        e.handle = p->cong.handle;
        e.a = p->cong.cong;
        break;
    default:
        return;
    }
    post(&e);
}
static void bt_cb(esp_bt_gap_cb_event_t t, esp_bt_gap_cb_param_t *p) {
    if (t == ESP_BT_GAP_PIN_REQ_EVT) {
        event e = {.type = E_PIN, .a = p->pin_req.min_16_digit};
        memcpy(e.data, p->pin_req.bda, 6);
        post(&e);
    }
}
static void ble_gap_cb(esp_gap_ble_cb_event_t t, esp_ble_gap_cb_param_t *p) {
    event e = {0};
    switch (t) {
    case ESP_GAP_BLE_SCAN_PARAM_SET_COMPLETE_EVT:
        simple(E_SCAN_PARAM, p->scan_param_cmpl.status, 0);
        return;
    case ESP_GAP_BLE_SCAN_RESULT_EVT:
        if (p->scan_rst.search_evt == ESP_GAP_SEARCH_INQ_CMPL_EVT) {
            simple(E_SCAN_DONE, 0, 0);
            return;
        }
        if (p->scan_rst.search_evt != ESP_GAP_SEARCH_INQ_RES_EVT)
            return;
        e.type = E_SCAN;
        e.data[0] = p->scan_rst.ble_addr_type;
        memcpy(e.data + 1, p->scan_rst.bda, 6);
        e.data[7] = (uint8_t)p->scan_rst.rssi;
        {
            uint8_t n = 0;
            uint8_t *name =
                esp_ble_resolve_adv_data(p->scan_rst.ble_adv, ESP_BLE_AD_TYPE_NAME_CMPL, &n);
            if (!name)
                name =
                    esp_ble_resolve_adv_data(p->scan_rst.ble_adv, ESP_BLE_AD_TYPE_NAME_SHORT, &n);
            if (n > 31)
                n = 31;
            e.len = 8 + n;
            if (name)
                memcpy(e.data + 8, name, n);
        }
        break;
    case ESP_GAP_BLE_SCAN_STOP_COMPLETE_EVT:
        simple(E_SCAN_STOP, p->scan_stop_cmpl.status, 0);
        return;
    case ESP_GAP_BLE_SCAN_START_COMPLETE_EVT:
        if (p->scan_start_cmpl.status)
            simple(E_SCAN_DONE, 0, 0);
        return;
    case ESP_GAP_BLE_PASSKEY_REQ_EVT:
        e.type = E_PASSKEY;
        memcpy(e.data, p->ble_security.ble_req.bd_addr, 6);
        break;
    case ESP_GAP_BLE_SEC_REQ_EVT:
        e.type = E_SECURITY;
        memcpy(e.data, p->ble_security.ble_req.bd_addr, 6);
        break;
    case ESP_GAP_BLE_AUTH_CMPL_EVT:
        e.type = E_AUTH;
        e.a = p->ble_security.auth_cmpl.success;
        memcpy(e.data, p->ble_security.auth_cmpl.bd_addr, 6);
        break;
    default:
        return;
    }
    post(&e);
}
static void gatt_cb(esp_gattc_cb_event_t t, esp_gatt_if_t g, esp_ble_gattc_cb_param_t *p) {
    event e = {0};
    switch (t) {
    case ESP_GATTC_REG_EVT:
        e.type = E_REG;
        e.a = p->reg.status;
        e.b = g;
        break;
    case ESP_GATTC_OPEN_EVT:
        e.type = E_OPEN;
        e.a = p->open.status;
        e.b = p->open.conn_id;
        memcpy(e.data, p->open.remote_bda, 6);
        break;
    case ESP_GATTC_CFG_MTU_EVT:
        e.type = E_MTU;
        e.a = p->cfg_mtu.status;
        e.b = p->cfg_mtu.mtu;
        e.c = p->cfg_mtu.conn_id;
        break;
    case ESP_GATTC_SEARCH_RES_EVT:
        if (p->search_res.srvc_id.uuid.len != ESP_UUID_LEN_128 ||
            memcmp(p->search_res.srvc_id.uuid.uuid.uuid128, service_uuid, 16))
            return;
        e.type = E_SERVICE;
        e.a = p->search_res.start_handle;
        e.b = p->search_res.end_handle;
        e.c = p->search_res.conn_id;
        break;
    case ESP_GATTC_SEARCH_CMPL_EVT:
        e.type = E_SEARCH_DONE;
        e.a = p->search_cmpl.status;
        e.c = p->search_cmpl.conn_id;
        break;
    case ESP_GATTC_REG_FOR_NOTIFY_EVT:
        e.type = E_NOTIFY_REG;
        e.a = p->reg_for_notify.status;
        e.b = p->reg_for_notify.handle;
        break;
    case ESP_GATTC_WRITE_DESCR_EVT:
        e.type = E_DESC_WRITTEN;
        e.a = p->write.status;
        e.c = p->write.conn_id;
        break;
    case ESP_GATTC_NOTIFY_EVT:
        if (p->notify.value_len > HUB_PAYLOAD) {
            __atomic_store_n(&overflow, 1, __ATOMIC_RELAXED);
            return;
        }
        e.type = E_BLE_RX;
        e.a = p->notify.handle;
        e.c = p->notify.conn_id;
        e.len = p->notify.value_len;
        memcpy(e.data, p->notify.value, e.len);
        break;
    case ESP_GATTC_WRITE_CHAR_EVT:
        e.type = E_BLE_WRITTEN;
        e.a = p->write.status;
        e.c = p->write.conn_id;
        break;
    case ESP_GATTC_DISCONNECT_EVT:
        e.type = E_BLE_DOWN;
        e.c = p->disconnect.conn_id;
        memcpy(e.data, p->disconnect.remote_bda, 6);
        break;
    default:
        return;
    }
    post(&e);
}
static bool discover_chars(void) {
    esp_bt_uuid_t uuid = {.len = ESP_UUID_LEN_128};
    memcpy(uuid.uuid.uuid128, service_uuid, 16);
    esp_gattc_char_elem_t ch;
    uint16_t count = 1;
    uuid.uuid.uuid128[12] = 2;
    if (esp_ble_gattc_get_char_by_uuid(gif, conn, svc_start, svc_end, uuid, &ch, &count) !=
            ESP_GATT_OK ||
        !count || !(ch.properties & ESP_GATT_CHAR_PROP_BIT_WRITE))
        return false;
    rx_handle = ch.char_handle;
    count = 1;
    uuid.uuid.uuid128[12] = 3;
    if (esp_ble_gattc_get_char_by_uuid(gif, conn, svc_start, svc_end, uuid, &ch, &count) !=
            ESP_GATT_OK ||
        !count || !(ch.properties & ESP_GATT_CHAR_PROP_BIT_NOTIFY))
        return false;
    tx_handle = ch.char_handle;
    return esp_ble_gattc_register_for_notify(gif, target, tx_handle) == ESP_OK;
}
static void handle(event *e) {
    int i;
    switch (e->type) {
    case E_USB:
        hub_feed(&hosts[0].parser, e->data, e->len, frame_in, (void *)0);
        break;
    case E_SPP_INIT:
        if (e->a == ESP_SPP_SUCCESS) {
            esp_bt_gap_set_device_name(NAME);
            esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_NON_DISCOVERABLE);
            esp_spp_start_srv(ESP_SPP_SEC_AUTHENTICATE | ESP_SPP_SEC_ENCRYPT, ESP_SPP_ROLE_SLAVE, 0, NAME);
        }
        break;
    case E_PIN:
        esp_bt_gap_pin_reply(e->data, now() < pair_until && (!e->a || pair_pin_len == 16),
                             pair_pin_len, pair_pin);
        break;
    case E_SPP_UP:
        if (e->a != ESP_SPP_SUCCESS)
            break;
        for (i = 1; i < HOSTS; i++)
            if (!hosts[i].online)
                break;
        if (i == HOSTS) {
            esp_spp_disconnect(e->handle);
            break;
        }
        output *storage = hosts[i].out;
        memset(&hosts[i], 0, sizeof(hosts[i]));
        hosts[i].out = storage;
        hosts[i].online = true;
        hosts[i].handle = e->handle;
        break;
    case E_SPP_DOWN:
        i = slot(e->handle);
        if (i >= 0)
            drop_host(i);
        break;
    case E_SPP_RX:
        i = slot(e->handle);
        if (i >= 0)
            hub_feed(&hosts[i].parser, e->data, e->len, frame_in, (void *)(intptr_t)i);
        break;
    case E_SPP_SENT:
        i = slot(e->handle);
        if (i >= 0) {
            host *h = &hosts[i];
            if (e->a != ESP_SPP_SUCCESS) {
                drop_host(i);
                break;
            }
            h->busy = false;
            h->congested = e->b;
            if (h->count) {
                h->head = (h->head + 1) % OUT_DEPTH;
                h->count--;
            }
        }
        break;
    case E_SPP_CONG:
        i = slot(e->handle);
        if (i >= 0)
            hosts[i].congested = e->a;
        break;
    case E_REG:
        if (e->a == ESP_GATT_OK) {
            gif = e->b;
            esp_ble_scan_params_t sp = {.scan_type = BLE_SCAN_TYPE_ACTIVE,
                                        .own_addr_type = BLE_ADDR_TYPE_PUBLIC,
                                        .scan_filter_policy = BLE_SCAN_FILTER_ALLOW_ALL,
                                        .scan_interval = 0x50,
                                        .scan_window = 0x30,
                                        .scan_duplicate = BLE_SCAN_DUPLICATE_ENABLE};
            esp_ble_gap_set_scan_params(&sp);
        }
        break;
    case E_SCAN_PARAM:
        scan_ready = e->a == ESP_BT_STATUS_SUCCESS;
        break;
    case E_SCAN:
        if (owner >= 0 && scanning) {
            hub_frame f = {.service = 0, .op = 0x90, .len = e->len};
            memcpy(f.data, e->data, e->len);
            send_frame(owner, &f);
        }
        break;
    case E_SCAN_DONE:
        scanning = false;
        notice(0x91, "scan complete");
        break;
    case E_SCAN_STOP:
        scanning = false;
        if (connect_after_scan) {
            connect_after_scan = false;
            if (owner >= 0 && !begin_connect())
                notice(0x92, "connect failed");
        }
        break;
    case E_OPEN:
        if (memcmp(target, e->data, 6))
            break;
        connecting = false;
        if (e->a != ESP_GATT_OK) {
            notice(0x92, "connect failed");
            break;
        }
        conn = e->b;
        connected = true;
        if (owner < 0) {
            disconnect_ble();
            break;
        }
        ble_deadline = now() + 15000000;
        if (esp_ble_set_encryption(target, ESP_BLE_SEC_ENCRYPT_MITM) != ESP_OK)
            disconnect_ble();
        break;
    case E_MTU:
        if (connected && e->c == conn) {
            if (e->a == ESP_GATT_OK)
                mtu = e->b;
            if (esp_ble_gattc_search_service(gif, conn, NULL) != ESP_OK)
                disconnect_ble();
        }
        break;
    case E_SERVICE:
        if (connected && e->c == conn) {
            svc_start = e->a;
            svc_end = e->b;
        }
        break;
    case E_SEARCH_DONE:
        if (connected && e->c == conn && (e->a != ESP_GATT_OK || !svc_start || !discover_chars())) {
            notice(0x92, "MeshCore service unavailable");
            disconnect_ble();
        }
        break;
    case E_NOTIFY_REG:
        if (!connected || e->b != tx_handle)
            break;
        {
            esp_bt_uuid_t uuid = {.len = ESP_UUID_LEN_16,
                                  .uuid.uuid16 = ESP_GATT_UUID_CHAR_CLIENT_CONFIG};
            esp_gattc_descr_elem_t d;
            uint16_t count = 1;
            if (e->a != ESP_GATT_OK ||
                esp_ble_gattc_get_descr_by_char_handle(gif, conn, tx_handle, uuid, &d, &count) !=
                    ESP_GATT_OK ||
                !count) {
                disconnect_ble();
                break;
            }
            cccd = d.handle;
            uint8_t enabled[] = {1, 0};
            if (esp_ble_gattc_write_char_descr(gif, conn, cccd, 2, enabled, ESP_GATT_WRITE_TYPE_RSP,
                                               ESP_GATT_AUTH_REQ_NONE) != ESP_OK)
                disconnect_ble();
        }
        break;
    case E_DESC_WRITTEN:
        if (connected && e->c == conn) {
            if (e->a == ESP_GATT_OK && owner >= 0) {
                ready = true;
                notice(0x93, "MeshCore ready");
            } else {
                notice(0x92, "notification subscription failed");
                disconnect_ble();
            }
        }
        break;
    case E_BLE_RX:
        if (ready && connected && e->c == conn && e->a == tx_handle && owner >= 0) {
            payload_activity();
            hub_frame f = {.service = 1, .op = 0x90, .len = e->len};
            memcpy(f.data, e->data, e->len);
            send_frame(owner, &f);
        }
        break;
    case E_BLE_WRITTEN:
        if (connected && e->c == conn && ble_pending) {
            ble_pending = false;
            hub_frame f = {.service = 1, .op = 1, .id = pending_id};
            reply(owner, &f, e->a == ESP_GATT_OK ? 0 : 4, NULL, 0);
        }
        break;
    case E_BLE_DOWN:
        if (!memcmp(target, e->data, 6)) {
            ready = connected = connecting = ble_pending = passkey_pending = false;
            notice(0x92, "BLE disconnected");
        }
        break;
    case E_PASSKEY:
        if (connected && owner >= 0 && !memcmp(target, e->data, 6)) {
            passkey_pending = true;
            ble_deadline = now() + 60000000;
            lease_until = ble_deadline;
            notice(0x94, "BLE passkey required");
        } else
            esp_ble_passkey_reply(e->data, false, 0);
        break;
    case E_SECURITY:
        esp_ble_gap_security_rsp(e->data, connected && owner >= 0 && !memcmp(target, e->data, 6));
        break;
    case E_AUTH:
        if (!connected || memcmp(target, e->data, 6))
            break;
        if (!e->a) {
            notice(0x92, "BLE authentication failed");
            disconnect_ble();
        } else if (!secured && owner >= 0) {
            secured = true;
            ble_deadline = now() + 15000000;
            if (esp_ble_gattc_send_mtu_req(gif, conn) != ESP_OK &&
                esp_ble_gattc_search_service(gif, conn, NULL) != ESP_OK)
                disconnect_ble();
        }
        break;
    }
}
static void usb_task(void *arg) {
    event e = {.type = E_USB};
    while (1) {
        int n = uart_read_bytes(UART_NUM_0, e.data, 256, pdMS_TO_TICKS(100));
        if (n > 0) {
            e.len = n;
            post(&e);
        }
    }
}
void app_main(void) {
    gpio_config_t leds = {.pin_bit_mask = (1ULL << 22) | (1ULL << 23) | (1ULL << 25),
                          .mode = GPIO_MODE_OUTPUT, .pull_up_en = GPIO_PULLUP_DISABLE,
                          .pull_down_en = GPIO_PULLDOWN_DISABLE, .intr_type = GPIO_INTR_DISABLE};
    ESP_ERROR_CHECK(gpio_config(&leds));
    gpio_set_level(GPIO_NUM_22, 0);
    gpio_set_level(GPIO_NUM_23, 0);
    gpio_set_level(GPIO_NUM_25, 0);
    /* Never erase bond/NVS data silently on an initialization error. */
    ESP_ERROR_CHECK(nvs_flash_init());
    events = xQueueCreate(48, sizeof(event));
    configASSERT(events);
    uart_config_t uc = {.baud_rate = 115200,
                        .data_bits = UART_DATA_8_BITS,
                        .parity = UART_PARITY_DISABLE,
                        .stop_bits = UART_STOP_BITS_1,
                        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
                        .source_clk = UART_SCLK_DEFAULT};
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0, &uc));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0, 1, 3, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 4096, 0, 0, NULL, 0));
    for (int i = 0; i < HOSTS; i++) {
        hosts[i].out =
            heap_caps_calloc(OUT_DEPTH, sizeof(output), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        configASSERT(hosts[i].out);
    }
    hosts[0].online = true;
    esp_bt_controller_config_t bc = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_bt_controller_init(&bc));
    ESP_ERROR_CHECK(esp_bt_controller_enable(ESP_BT_MODE_BTDM));
    esp_bluedroid_config_t bluedroid = BT_BLUEDROID_INIT_CONFIG_DEFAULT();
    bluedroid.ssp_en = false; /* N810 legacy PIN pairing; BLE security remains enabled. */
    ESP_ERROR_CHECK(esp_bluedroid_init_with_cfg(&bluedroid));
    ESP_ERROR_CHECK(esp_bluedroid_enable());
    ESP_ERROR_CHECK(esp_bt_gap_register_callback(bt_cb));
    ESP_ERROR_CHECK(esp_spp_register_callback(spp_cb));
    esp_bt_pin_code_t unused = {0};
    ESP_ERROR_CHECK(esp_bt_gap_set_pin(ESP_BT_PIN_TYPE_VARIABLE, 0, unused));
    esp_spp_cfg_t sc = {.mode = ESP_SPP_MODE_CB, .enable_l2cap_ertm = false, .tx_buffer_size = 0};
    ESP_ERROR_CHECK(esp_spp_enhanced_init(&sc));
    ESP_ERROR_CHECK(esp_ble_gap_register_callback(ble_gap_cb));
    ESP_ERROR_CHECK(esp_ble_gattc_register_callback(gatt_cb));
    uint8_t auth = ESP_LE_AUTH_REQ_SC_MITM_BOND, io = ESP_IO_CAP_IN, key_size = 16;
    esp_ble_gap_set_security_param(ESP_BLE_SM_AUTHEN_REQ_MODE, &auth, 1);
    esp_ble_gap_set_security_param(ESP_BLE_SM_IOCAP_MODE, &io, 1);
    esp_ble_gap_set_security_param(ESP_BLE_SM_MAX_KEY_SIZE, &key_size, 1);
    ESP_ERROR_CHECK(esp_ble_gatt_set_local_mtu(517));
    ESP_ERROR_CHECK(esp_ble_gattc_app_register(0));
    xTaskCreate(usb_task, "usb-rx", 3072, NULL, 5, NULL);
    event e;
    while (1) {
        if (__atomic_exchange_n(&overflow, 0,
                                __ATOMIC_RELAXED)) { /* Event loss invalidates connection state.
                                                        Fail closed; never replay. */
            esp_restart();
        }
        if (xQueueReceive(events, &e, pdMS_TO_TICKS(2)))
            handle(&e);
        if (owner >= 0 && now() > lease_until) {
            notice(0x92, "owner lease expired");
            lose_owner();
        }
        if (pair_until && now() > pair_until) {
            pair_until = 0;
            memset(pair_pin, 0, sizeof(pair_pin));
            pair_pin_len = 0;
            esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_NON_DISCOVERABLE);
        }
        if ((connecting || (connected && !ready) || ble_pending) && now() > ble_deadline) {
            notice(0x92, "BLE operation timed out");
            disconnect_ble();
            ble_deadline = now() + 10000000;
        }
        if(lora_owner>=0&&now()>lora_lease){
            lora_enable(false);lora_owner=-1;lora_request=0;
        }
        lora_poll(lora_received,lora_completed);
        pump();
        update_leds();
    }
}
