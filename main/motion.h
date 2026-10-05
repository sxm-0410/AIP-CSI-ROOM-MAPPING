/* Motion detection on a stream of RSSI samples. Pure C, no ESP-IDF deps, so it
 * can be unit-tested on the host (see test/host/). */
#pragma once
#include <stdint.h>

#define MOTION_MAX_WINDOW 64

typedef enum { MOTION_CALIBRATING = 0, MOTION_IDLE, MOTION_ACTIVE } motion_state_t;

typedef struct {
    int window;            /* samples per sliding window (<= MOTION_MAX_WINDOW) */
    int calib_samples;     /* windows to learn the empty-room baseline from */
    float k_sigma;         /* threshold = mean_std + k_sigma * std_of_std */
    float min_std_margin;  /* ...but at least this many dB above mean_std */
    float level_shift_db;  /* |window mean - baseline mean| alarm (blocked path) */
    int hold_ms;           /* keep ACTIVE this long after last trigger */
} motion_cfg_t;

typedef struct {
    motion_cfg_t cfg;
    float buf[MOTION_MAX_WINDOW];
    int n, head;
    int calib_seen;
    double sum_std, sum_std2, sum_mean;
    float base_mean, thr_std;
    int64_t hold_until_ms;
    float last_std, last_mean;
    motion_state_t state;
} motion_t;

void motion_init(motion_t *m, const motion_cfg_t *cfg);
/* Restart calibration (room must be empty). */
void motion_recalibrate(motion_t *m);
motion_state_t motion_update(motion_t *m, float rssi_dbm, int64_t now_ms);
