#include "csi_stream.h"
#include <stdio.h>
#include <string.h>
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "lwip/inet.h"
#include "ping/ping_sock.h"

#define MAX_BYTES 384          /* LLTF only = 128; headroom for HT-LTF */

static const char *TAG = "csi";
static QueueHandle_t q;
static uint32_t seq;
static volatile uint32_t dropped;

typedef struct { int8_t d[MAX_BYTES]; int len; int rssi; int64_t ms; } csi_msg_t;

/* Runs in the Wi-Fi task: copy and return fast; printing happens elsewhere. */
static void csi_cb(void *ctx, wifi_csi_info_t *info)
{
    if (!info || !info->buf || info->len <= 0) return;
    csi_msg_t m;
    m.len = info->len > MAX_BYTES ? MAX_BYTES : info->len;
    m.rssi = info->rx_ctrl.rssi;
    m.ms = esp_timer_get_time() / 1000;
    memcpy(m.d, info->buf, m.len);
    if (xQueueSend(q, &m, 0) != pdTRUE) dropped++;
}

/* Build the whole row first and emit it with ONE fwrite: separate printf calls per
 * value let the motion task's output land in the middle of a row. */
static void print_task(void *arg)
{
    static char line[MAX_BYTES * 5 + 96];
    csi_msg_t m;
    while (xQueueReceive(q, &m, portMAX_DELAY)) {
        int n = snprintf(line, sizeof line, "CSI_DATA,%lu,%lld,%d,%d,[", (unsigned long)seq++,
                         (long long)m.ms, m.rssi, m.len);
        for (int i = 0; i < m.len && n < (int)sizeof line - 8; i++)
            n += snprintf(line + n, sizeof line - n, "%d%s", m.d[i], i + 1 < m.len ? "," : "");
        n += snprintf(line + n, sizeof line - n, "]\n");
        fwrite(line, 1, n, stdout);
    }
}

void csi_stream_start(void)
{
    q = xQueueCreate(24, sizeof(csi_msg_t));
    /* LLTF only: fixed 64-subcarrier frame, so every row has the same length */
    wifi_csi_config_t cfg = { .lltf_en = true, .htltf_en = false, .stbc_htltf2_en = false,
                              .ltf_merge_en = true, .channel_filter_en = false,
                              .manu_scale = false };
    /* Log instead of abort: a failure here must not boot-loop the whole device. */
    esp_err_t e = esp_wifi_set_csi_config(&cfg);
    if (e == ESP_OK) e = esp_wifi_set_csi_rx_cb(csi_cb, NULL);
    if (e == ESP_OK) e = esp_wifi_set_csi(true);
    if (e != ESP_OK) {
        ESP_LOGE(TAG, "CSI setup failed (%s). Is CONFIG_ESP_WIFI_CSI_ENABLED=y?",
                 esp_err_to_name(e));
        return;
    }
    xTaskCreate(print_task, "csi_print", 4096, NULL, 4, NULL);
    ESP_LOGI(TAG, "CSI streaming on");
}

static esp_ping_handle_t s_ping;
static volatile uint32_t s_ok, s_timeout;
static int s_interval_ms;
static uint32_t s_restarts;

static void on_ok(esp_ping_handle_t h, void *a) { s_ok++; }
static void on_timeout(esp_ping_handle_t h, void *a) { s_timeout++; }

static bool ping_session_start(void)
{
    esp_netif_t *nif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_ip_info_t ip;
    if (!nif || esp_netif_get_ip_info(nif, &ip) != ESP_OK || !ip.gw.addr) {
        ESP_LOGW(TAG, "no gateway yet; probe not started");
        return false;
    }
    esp_ping_config_t pc = ESP_PING_DEFAULT_CONFIG();
    pc.count = ESP_PING_COUNT_INFINITE;
    pc.interval_ms = s_interval_ms;
    pc.data_size = 1;
    pc.timeout_ms = 500;
    ip_addr_t gw = { 0 };
    ip_2_ip4(&gw)->addr = ip.gw.addr;
    IP_SET_TYPE_VAL(gw, IPADDR_TYPE_V4);
    pc.target_addr = gw;
    esp_ping_callbacks_t cb = { .on_ping_success = on_ok, .on_ping_timeout = on_timeout };
    if (esp_ping_new_session(&pc, &cb, &s_ping) != ESP_OK) return false;
    return esp_ping_start(s_ping) == ESP_OK;
}

/* Routers may stop answering a fast ping stream (flood protection). If replies dry up,
 * rebuild the session; log stats so a stall is visible instead of silent. */
static void probe_watch(void *arg)
{
    uint32_t last_ok = 0;
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(3000));
        ESP_LOGI(TAG, "probe ok=%lu timeout=%lu restarts=%lu csi_dropped=%lu",
                 (unsigned long)s_ok, (unsigned long)s_timeout,
                 (unsigned long)s_restarts, (unsigned long)dropped);
        if (s_ok == last_ok && s_ping) {                     /* no replies for 3 s */
            esp_ping_stop(s_ping);
            esp_ping_delete_session(s_ping);
            s_ping = NULL;
            s_restarts++;
            ping_session_start();
        }
        last_ok = s_ok;
    }
}

void probe_start(int interval_ms)
{
    s_interval_ms = interval_ms;
    if (ping_session_start())
        xTaskCreate(probe_watch, "probe_watch", 3072, NULL, 3, NULL);
}
