#include "oled.h"
#include <string.h>
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "font5x7.h"

static const char *TAG = "oled";

#define W 128
#define H CONFIG_MOTION_OLED_HEIGHT
#define PAGES (H / 8)

static i2c_master_bus_handle_t s_bus;
static i2c_master_dev_handle_t s_dev;
static uint8_t s_fb[W * PAGES];
static int s_fail;                  /* consecutive failed transfers */
static bool s_dead;                 /* too many failures: stop talking to the display */

/* Pin pairs seen on common ESP32 boards / OLED slots (same list as oled_scan). */
static const int pairs[][2] = {
    {21,22},{22,21},{4,15},{5,4},{16,17},{17,16},
    {13,14},{14,13},{32,33},{33,32},{23,19},{25,26},{26,25},{18,19}
};

static bool xfer(const uint8_t *b, size_t n)
{
    if (s_dead) return false;
    bool ok = i2c_master_transmit(s_dev, b, n, 100) == ESP_OK;
    if (ok) s_fail = 0;
    else if (++s_fail >= 8) {
        s_dead = true;
        ESP_LOGE(TAG, "display stopped answering; disabling it (check wiring/pull-ups)");
    }
    return ok;
}

static bool cmd(uint8_t c)
{
    uint8_t b[2] = { 0x00, c };
    return xfer(b, 2);
}

static bool try_pair(int sda, int scl, int addr, int rst)
{
    if (rst >= 0) {                       /* Heltec-style boards need a reset pulse */
        gpio_set_direction(rst, GPIO_MODE_OUTPUT);
        gpio_set_level(rst, 0); vTaskDelay(pdMS_TO_TICKS(20));
        gpio_set_level(rst, 1); vTaskDelay(pdMS_TO_TICKS(20));
    }
    i2c_master_bus_config_t bc = {
        .clk_source = I2C_CLK_SRC_DEFAULT, .i2c_port = -1,
        .sda_io_num = sda, .scl_io_num = scl, .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    if (i2c_new_master_bus(&bc, &s_bus) != ESP_OK) return false;
    esp_err_t pr = ESP_FAIL;
    for (int t = 0; t < 3 && pr != ESP_OK; t++) {      /* panel may still be powering up */
        pr = i2c_master_probe(s_bus, addr, 100);
        if (pr != ESP_OK) vTaskDelay(pdMS_TO_TICKS(60));
    }
    if (pr != ESP_OK) {
        i2c_del_master_bus(s_bus);
        s_bus = NULL;
        return false;
    }
    i2c_device_config_t dc = { .dev_addr_length = I2C_ADDR_BIT_LEN_7,
                               .device_address = addr, .scl_speed_hz = 100000 };
    if (i2c_master_bus_add_device(s_bus, &dc, &s_dev) != ESP_OK) {
        i2c_del_master_bus(s_bus);
        s_bus = NULL;
        return false;
    }
    ESP_LOGI(TAG, "OLED found at 0x%02X on SDA=%d SCL=%d (reset=%d)", addr, sda, scl, rst);
    return true;
}

bool oled_init(void)
{
    bool ok = try_pair(CONFIG_MOTION_OLED_SDA, CONFIG_MOTION_OLED_SCL,
                       CONFIG_MOTION_OLED_ADDR, CONFIG_MOTION_OLED_RST);
    for (size_t i = 0; !ok && i < sizeof(pairs) / sizeof(pairs[0]); i++) {
        for (int addr = 0x3C; addr <= 0x3D && !ok; addr++) {
            int rst = (pairs[i][0] == 4 && pairs[i][1] == 15) ? 16 : -1;
            ok = try_pair(pairs[i][0], pairs[i][1], addr, rst);
        }
    }
    if (!ok) {
        ESP_LOGW(TAG, "no SSD1306 found; running without display");
        return false;
    }
    ESP_LOGI(TAG, "tip: set these pins in menuconfig to skip the scan at boot");
    const uint8_t init[] = {
        0xAE, 0xD5, 0x80, 0xA8, (uint8_t)(H - 1), 0xD3, 0x00, 0x40, 0x8D, 0x14,
        0x20, 0x00, 0xA1, 0xC8, 0xDA, (uint8_t)(H == 64 ? 0x12 : 0x02),
        0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF,
    };
    for (size_t i = 0; i < sizeof(init); i++) cmd(init[i]);
    if (s_dead) return false;
    oled_clear();
    oled_flush();
    return true;
}

int oled_width(void) { return W; }
int oled_height(void) { return H; }
void oled_clear(void) { memset(s_fb, 0, sizeof(s_fb)); }

static void px(int x, int y)
{
    if (x < 0 || y < 0 || x >= W || y >= H) return;
    s_fb[(y / 8) * W + x] |= 1 << (y & 7);
}

void oled_rect(int x, int y, int w, int h, bool fill)
{
    for (int j = 0; j < h; j++)
        for (int i = 0; i < w; i++)
            if (fill || i == 0 || j == 0 || i == w - 1 || j == h - 1) px(x + i, y + j);
}

void oled_text(int x, int y, int scale, const char *s)
{
    for (; *s; s++, x += 6 * scale) {
        char c = *s;
        if (c >= 'a' && c <= 'z') c -= 32;
        if (c < 0x20 || c > 0x5F) c = '?';
        const unsigned char *g = font5x7[c - 0x20];
        for (int col = 0; col < 5; col++)
            for (int row = 0; row < 7; row++)
                if (g[col] & (1 << row))
                    oled_rect(x + col * scale, y + row * scale, scale, scale, true);
    }
}

void oled_flush(void)
{
    if (!s_dev || s_dead) return;
    cmd(0x21); cmd(0); cmd(W - 1);          /* column range */
    cmd(0x22); cmd(0); cmd(PAGES - 1);      /* page range */
    uint8_t row[W + 1];
    row[0] = 0x40;                          /* data prefix */
    for (int p = 0; p < PAGES; p++) {
        memcpy(row + 1, &s_fb[p * W], W);
        xfer(row, sizeof(row));
    }
}
