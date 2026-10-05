/* Wi-Fi path monitor: joins the router, samples its RSSI, runs the motion detector
 * (motion.c) and reports the result on the serial port, the OLED and the optional LED.
 * Based on the ESP-IDF "fast scan" example. */
#include "freertos/FreeRTOS.h"
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

#define DEFAULT_SSID CONFIG_EXAMPLE_WIFI_SSID
#define DEFAULT_PWD CONFIG_EXAMPLE_WIFI_PASSWORD

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
            snprintf(line, sizeof line, "KEEP ROOM EMPTY %d%%", motion_progress_pct(m));
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
 * feeds it in, drives the LED/OLED and prints the MOTION line read by the PC tools. */
static motion_t s_motion;                  /* ~3 KB of history: too big for the task stack */

static void motion_task(void *param)
{
    motion_cfg_t cfg = {
        .window = CONFIG_MOTION_WINDOW,
        .calib_samples = CONFIG_MOTION_CALIB_SAMPLES,
        .k_sigma = CONFIG_MOTION_K_SIGMA_X10 / 10.0f,
        .min_std_margin = CONFIG_MOTION_MIN_STD_MARGIN_X10 / 10.0f,
        .level_shift_db = CONFIG_MOTION_LEVEL_SHIFT_DB,
        .hold_ms = CONFIG_MOTION_HOLD_MS,
    };
    motion_t *m = &s_motion;
    motion_init(m, &cfg);
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
            motion_state_t prev = m->state;
            motion_state_t st = motion_update(m, ap.rssi, now);
            if (st == MOTION_CALIBRATING)
                gpio_set_level(LED_GPIO, (blink++ / 3) & 1);   /* blink */
            else
                gpio_set_level(LED_GPIO, st == MOTION_ACTIVE);
            if (prev == MOTION_CALIBRATING && st != MOTION_CALIBRATING)
                ESP_LOGI(TAG, "calibrated: base=%.1f dBm thr_std=%.2f dB thr_level=%.2f dB",
                         m->base_mean, m->thr_std, m->thr_level);
            /* MOTION,<ms>,<rssi>,<std>,<state>,<thr_std>,<base_rssi>,<learn_pct> */
            printf("MOTION,%lld,%d,%.2f,%d,%.2f,%.1f,%d\n", (long long)now, ap.rssi,
                   m->last_std, (int)st, m->thr_std, m->base_mean, motion_progress_pct(m));
#if CONFIG_MOTION_OLED
            if (have_oled && (tick % 3 == 0 || st != prev)) show(m, ap.rssi, st);
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
            xTaskCreate(motion_task, "motion", 6144, NULL, 5, NULL);
#if CONFIG_MOTION_PROBE_TRAFFIC
            probe_start(CONFIG_MOTION_PROBE_MS);
#endif
#if CONFIG_CSI_STREAM
            csi_stream_start();
#endif
        }
    }
}


/* Initialize Wi-Fi as a station and start connecting. */
static void fast_scan(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &event_handler, NULL, NULL));

    // Initialize default station as network interface instance (esp-netif)
    ESP_ERROR_CHECK(esp_netif_create_default_wifi_sta() ? ESP_OK : ESP_FAIL);

    // Initialize and start WiFi
    wifi_config_t wifi_config = {
        .sta = {
            .ssid = DEFAULT_SSID,
            .password = DEFAULT_PWD,
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
