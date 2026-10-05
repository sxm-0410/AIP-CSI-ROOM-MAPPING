/* Scan Example

   This example code is in the Public Domain (or CC0 licensed, at your option.)

   Unless required by applicable law or agreed to in writing, this
   software is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
   CONDITIONS OF ANY KIND, either express or implied.
*/

/*
    This example shows how to use the All Channel Scan or Fast Scan to connect
    to a Wi-Fi network.

    In the Fast Scan mode, the scan will stop as soon as the first network matching
    the SSID is found. In this mode, an application can set threshold for the
    authentication mode and the Signal strength. Networks that do not meet the
    threshold requirements will be ignored.

    In the All Channel Scan mode, the scan will end only after all the channels
    are scanned, and connection will start with the best network. The networks
    can be sorted based on Authentication Mode or Signal Strength. The priority
    for the Authentication mode is:  WPA2 > WPA > WEP > Open
*/
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "esp_wifi.h"
#include "esp_log.h"
#include "esp_event.h"
#include "nvs_flash.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_netif.h"
#include "motion.h"
#include "csi_stream.h"
#include "oled.h"
#include <stdio.h>

/* Set the SSID and Password via project configuration, or can set directly here */
#define DEFAULT_SSID CONFIG_EXAMPLE_WIFI_SSID
#define DEFAULT_PWD CONFIG_EXAMPLE_WIFI_PASSWORD

#if CONFIG_EXAMPLE_WIFI_ALL_CHANNEL_SCAN
#define DEFAULT_SCAN_METHOD WIFI_ALL_CHANNEL_SCAN
#elif CONFIG_EXAMPLE_WIFI_FAST_SCAN
#define DEFAULT_SCAN_METHOD WIFI_FAST_SCAN
#else
#define DEFAULT_SCAN_METHOD WIFI_FAST_SCAN
#endif /*CONFIG_EXAMPLE_SCAN_METHOD*/

#if CONFIG_EXAMPLE_WIFI_CONNECT_AP_BY_SIGNAL
#define DEFAULT_SORT_METHOD WIFI_CONNECT_AP_BY_SIGNAL
#elif CONFIG_EXAMPLE_WIFI_CONNECT_AP_BY_SECURITY
#define DEFAULT_SORT_METHOD WIFI_CONNECT_AP_BY_SECURITY
#else
#define DEFAULT_SORT_METHOD WIFI_CONNECT_AP_BY_SIGNAL
#endif /*CONFIG_EXAMPLE_SORT_METHOD*/

#if CONFIG_EXAMPLE_FAST_SCAN_THRESHOLD
#define DEFAULT_RSSI CONFIG_EXAMPLE_FAST_SCAN_MINIMUM_SIGNAL
#if CONFIG_EXAMPLE_FAST_SCAN_WEAKEST_AUTHMODE_OPEN
#define DEFAULT_AUTHMODE WIFI_AUTH_OPEN
#elif CONFIG_EXAMPLE_FAST_SCAN_WEAKEST_AUTHMODE_WEP
#define DEFAULT_AUTHMODE WIFI_AUTH_WEP
#elif CONFIG_EXAMPLE_FAST_SCAN_WEAKEST_AUTHMODE_WPA
#define DEFAULT_AUTHMODE WIFI_AUTH_WPA_PSK
#elif CONFIG_EXAMPLE_FAST_SCAN_WEAKEST_AUTHMODE_WPA2
#define DEFAULT_AUTHMODE WIFI_AUTH_WPA2_PSK
#else
#define DEFAULT_AUTHMODE WIFI_AUTH_OPEN
#endif
#else
#define DEFAULT_RSSI -127
#define DEFAULT_AUTHMODE WIFI_AUTH_OPEN
#endif /*CONFIG_EXAMPLE_FAST_SCAN_THRESHOLD*/

static const char *TAG = "scan";

#define LED_GPIO ((gpio_num_t)CONFIG_MOTION_LED_GPIO)

static char s_ip[16] = "";

#if CONFIG_MOTION_OLED
/* Redraw the status screen. Called from the sampling task only. */
static void show(const motion_t *m, int rssi, motion_state_t st)
{
    char line[24];
    const bool tall = oled_height() >= 64;
    oled_clear();
    oled_text(2, 2, 2, st == MOTION_CALIBRATING ? "LEARNING" :
                       st == MOTION_ACTIVE ? "MOTION!" : "IDLE");
    snprintf(line, sizeof line, "RSSI %d DBM", rssi);
    oled_text(2, tall ? 22 : 20, 1, line);
    if (tall) {
        if (st == MOTION_CALIBRATING) {
            int pct = 100 * m->calib_seen / (m->cfg.calib_samples ? m->cfg.calib_samples : 1);
            snprintf(line, sizeof line, "KEEP ROOM EMPTY %d%%", pct);
        } else {
            snprintf(line, sizeof line, "STD %.2f / %.2f", m->last_std, m->thr_std);
        }
        oled_text(2, 34, 1, line);
        if (st != MOTION_CALIBRATING) {
            snprintf(line, sizeof line, "BASE %.1f DBM", m->base_mean);
            oled_text(2, 44, 1, line);
        }
        oled_text(2, 55, 1, s_ip[0] ? s_ip : "NO IP");
    }
    if (st == MOTION_ACTIVE) oled_rect(0, 0, oled_width(), oled_height(), false);
    oled_flush();
}
#endif

/* Detection logic lives in motion.c (host-testable). This task only samples RSSI,
 * feeds it in and drives the LED. Prints "MOTION,<ms>,<rssi>,<std>,<state>" for
 * tools/monitor.py. */
void MotionDetector(void *param)
{
    motion_cfg_t cfg = {
        .window = CONFIG_MOTION_WINDOW,
        .calib_samples = CONFIG_MOTION_CALIB_SAMPLES,
        .k_sigma = CONFIG_MOTION_K_SIGMA_X10 / 10.0f,
        .min_std_margin = CONFIG_MOTION_MIN_STD_MARGIN_X10 / 10.0f,
        .level_shift_db = CONFIG_MOTION_LEVEL_SHIFT_DB,
        .hold_ms = CONFIG_MOTION_HOLD_MS,
    };
    motion_t m;
    motion_init(&m, &cfg);
    int tick = 0, blink = 0;
#if CONFIG_MOTION_OLED
    bool have_oled = oled_init();
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);   /* the pin scan may have touched it */
#endif
    ESP_LOGI(TAG, "calibrating: keep the room empty");

    while (1) {
        wifi_ap_record_t ap;
        esp_err_t err = esp_wifi_sta_get_ap_info(&ap);
        if (err == ESP_OK) {
            tick++;
            int64_t now = esp_timer_get_time() / 1000;
            motion_state_t prev = m.state;
            motion_state_t st = motion_update(&m, ap.rssi, now);
            if (st == MOTION_CALIBRATING)
                gpio_set_level(LED_GPIO, (blink++ / 3) & 1);   /* blink */
            else
                gpio_set_level(LED_GPIO, st == MOTION_ACTIVE);
            if (prev == MOTION_CALIBRATING && st != MOTION_CALIBRATING)
                ESP_LOGI(TAG, "calibrated: base=%.1f dBm thr_std=%.2f dB",
                         m.base_mean, m.thr_std);
            int pct = st == MOTION_CALIBRATING
                          ? 100 * m.calib_seen / (m.cfg.calib_samples ? m.cfg.calib_samples : 1)
                          : 100;
            /* MOTION,<ms>,<rssi>,<std>,<state>,<thr_std>,<base_rssi>,<learn_pct> */
            printf("MOTION,%lld,%d,%.2f,%d,%.2f,%.1f,%d\n", (long long)now, ap.rssi,
                   m.last_std, (int)st, m.thr_std, m.base_mean, pct);
#if CONFIG_MOTION_OLED
            if (have_oled && (tick % 3 == 0 || st != prev)) show(&m, ap.rssi, st);
#endif
        } else {
            printf("Failed to get Wi-Fi AP info: %d\n", err);
        }
        vTaskDelay(pdMS_TO_TICKS(CONFIG_MOTION_SAMPLE_MS));
    }
}

static void event_handler(void* arg, esp_event_base_t event_base,
                                int32_t event_id, void* event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        ESP_LOGI(TAG, "got ip:" IPSTR, IP2STR(&event->ip_info.ip));
        snprintf(s_ip, sizeof s_ip, IPSTR, IP2STR(&event->ip_info.ip));

        static bool started;                  /* GOT_IP fires again after every reconnect */
        if (!started) {
            started = true;
            xTaskCreate(&MotionDetector, "MotionDetector", 4096, NULL, 5, NULL);
#if CONFIG_MOTION_PROBE_TRAFFIC
            probe_start(CONFIG_MOTION_PROBE_MS);
#endif
#if CONFIG_CSI_STREAM
            csi_stream_start();
#endif
        }
    }
}


/* Initialize Wi-Fi as sta and set scan method */
static void fast_scan(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &event_handler, NULL, NULL));

    // Initialize default station as network interface instance (esp-netif)
    esp_netif_t *sta_netif = esp_netif_create_default_wifi_sta();
    assert(sta_netif);

    // Initialize and start WiFi
    wifi_config_t wifi_config = {
        .sta = {
            .ssid = DEFAULT_SSID,
            .password = DEFAULT_PWD,
            .scan_method = DEFAULT_SCAN_METHOD,
            .sort_method = DEFAULT_SORT_METHOD,
            .threshold.rssi = DEFAULT_RSSI,
            .threshold.authmode = DEFAULT_AUTHMODE,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
    /* Modem sleep wakes only on beacons (~100 ms): CSI/RSSI would arrive in bursts. */
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
}

void app_main(void)
{
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);
    // Initialize NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK( ret );

    fast_scan();
}
