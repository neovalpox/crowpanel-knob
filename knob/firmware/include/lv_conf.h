// Config LVGL minimale : tout ce qui n'est pas défini ici prend la valeur par défaut.
#ifndef LV_CONF_H
#define LV_CONF_H
#include <stdint.h>

#define LV_COLOR_DEPTH 16
#define LV_COLOR_16_SWAP 0
#define LV_MEM_SIZE (72U * 1024U)

#define LV_TICK_CUSTOM 1
#define LV_TICK_CUSTOM_INCLUDE "Arduino.h"
#define LV_TICK_CUSTOM_SYS_TIME_EXPR (millis())

#define LV_DISP_DEF_REFR_PERIOD 15
#define LV_INDEV_DEF_READ_PERIOD 15
#define LV_INDEV_DEF_SCROLL_LIMIT 8
#define LV_INDEV_DEF_GESTURE_LIMIT 40

#define LV_USE_LOG 0

// Si LVGL manque de mémoire (ou autre assertion), on redémarre au lieu de rester figé.
#define LV_ASSERT_HANDLER_INCLUDE <esp_system.h>
#define LV_ASSERT_HANDLER esp_restart();
#define LV_USE_PERF_MONITOR 0

#define LV_FONT_MONTSERRAT_14 1
#define LV_FONT_MONTSERRAT_20 1
#define LV_FONT_MONTSERRAT_28 1
#define LV_FONT_MONTSERRAT_48 1
#define LV_FONT_DEFAULT &lv_font_montserrat_14

#define LV_THEME_DEFAULT_DARK 1
#define LV_IMG_CACHE_DEF_SIZE 0

#endif
