idf_component_register(SRCS "hub.c" "wire.c" "lora.c" INCLUDE_DIRS "." REQUIRES bt nvs_flash driver esp_timer)
