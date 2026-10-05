#pragma once
#include <stdbool.h>
#include <stdint.h>

/* Minimal SSD1306 (128x64 or 128x32, I2C) text display. Single-task use only. */

/* Try the configured SDA/SCL/address; if nothing answers, scan common pin pairs.
 * Returns false when no display is found (callers just skip drawing). */
bool oled_init(void);
void oled_clear(void);
/* ASCII text at pixel (x, y); lowercase is drawn as uppercase. scale 1 = 5x7 px. */
void oled_text(int x, int y, int scale, const char *s);
void oled_rect(int x, int y, int w, int h, bool fill);
void oled_flush(void);
int oled_width(void);
int oled_height(void);
