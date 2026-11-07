#pragma once
#include <esp_idf_version.h>
#if ESP_IDF_VERSION != ESP_IDF_VERSION_VAL(4,4,7)
#error "Scoped UART override requires exact ESP-IDF4.4.7"
#endif
#ifdef __cplusplus
extern "C" {
#endif
void htit_uart_iram_driver_link_anchor(void);
#ifdef __cplusplus
}
#endif
