/* Motion detection on a stream of RSSI samples. Pure C, no ESP-IDF deps, so it
 * can be unit-tested on the host (see test/host/). */
#pragma once
#include <stdint.h>

#define MOTION_MAX_WINDOW 64
#define MOTION_MAX_CALIB 200
#ifndef MOTION_QUIET_PCT
#define MOTION_QUIET_PCT 60    /* % of learning windows (the quietest) used to set the limits */
#endif
#ifndef MOTION_STD_FLOOR_X
#define MOTION_STD_FLOOR_X 2.0f   /* variation limit is at least this multiple of its normal level */
#endif
#define MOTION_FAST 4          /* samples in the short mean used for the level-shift check */

typedef enum { MOTION_CALIBRATING = 0, MOTION_IDLE, MOTION_ACTIVE } motion_state_t;

typedef struct {
    int window;            /* samples per sliding window, MOTION_FAST..MOTION_MAX_WINDOW */
    int calib_samples;     /* windows to learn the empty path from, <= MOTION_MAX_CALIB */
    float k_sigma;         /* limits = median + k_sigma * robust spread of the empty path */
    float min_std_margin;  /* the variation limit is at least this far above its median (dB) */
    float level_shift_db;  /* the level limit never goes below this (dB) */
    int hold_ms;           /* keep ACTIVE this long after the last trigger */
} motion_cfg_t;

typedef struct {
    motion_cfg_t cfg;
    float buf[MOTION_MAX_WINDOW];
    int n, head;
    int calib_seen;
    float std_hist[MOTION_MAX_CALIB], mean_hist[MOTION_MAX_CALIB], fast_hist[MOTION_MAX_CALIB];
    float base_mean, thr_std, thr_level;
    int64_t hold_until_ms;
    float last_std, last_mean, last_fast;
    motion_state_t state;
} motion_t;

void motion_init(motion_t *m, const motion_cfg_t *cfg);
motion_state_t motion_update(motion_t *m, float rssi_dbm, int64_t now_ms);
/* 0..100 while learning the empty path, 100 afterwards. */
int motion_progress_pct(const motion_t *m);
