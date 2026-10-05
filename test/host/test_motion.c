/* Host test: cc -Wall -Imain test/host/test_motion.c main/motion.c -lm -o /tmp/tm && /tmp/tm
 * Signals mimic the real board: integer-ish RSSI with several dB of jitter at 10 Hz. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "motion.h"

static float jitter(float amp) { return ((rand() % 2001) - 1000) / 1000.0f * amp; }

static motion_cfg_t cfg(void)
{
    return (motion_cfg_t){ .window = 10, .calib_samples = 100, .k_sigma = 4,
                           .min_std_margin = 0.5f, .level_shift_db = 2, .hold_ms = 2000 };
}

/* Feed `n` samples of (level + jitter(amp)); returns how many reported ACTIVE. */
static int feed(motion_t *m, int64_t *t, int n, float level, float amp)
{
    int active = 0;
    for (int i = 0; i < n; i++, *t += 100)
        active += motion_update(m, level + jitter(amp), *t) == MOTION_ACTIVE;
    return active;
}

/* Samples until the first ACTIVE report (or -1). */
static int latency(motion_t *m, int64_t *t, int max, float level, float amp)
{
    for (int i = 0; i < max; i++, *t += 100)
        if (motion_update(m, level + jitter(amp), *t) == MOTION_ACTIVE) return i + 1;
    return -1;
}

int main(void)
{
    srand(7);
    motion_cfg_t c = cfg();
    motion_t m;
    int64_t t = 0;

    /* 1. Learning disturbed by movement for ~40% of the time still gives a sane limit. */
    motion_init(&m, &c);
    assert(motion_progress_pct(&m) == 0);
    feed(&m, &t, 30, -45, 2.0f);
    feed(&m, &t, 40, -45, 9.0f);                       /* someone walks by while learning */
    int prev = 0;
    for (int i = 0; i < 200 && m.state == MOTION_CALIBRATING; i++, t += 100) {
        motion_update(&m, -45 + jitter(2.0f), t);
        int p = motion_progress_pct(&m);
        assert(p >= prev && p <= 100);
        prev = p;
    }
    assert(m.state != MOTION_CALIBRATING && motion_progress_pct(&m) == 100);
    feed(&m, &t, 40, -45, 2.0f);                       /* let any trailing hold expire */
    assert(m.state == MOTION_IDLE);
    printf("learned: base %.1f thr_std %.2f thr_level %.2f\n", m.base_mean, m.thr_std, m.thr_level);
    assert(m.thr_std < 4.0f);                           /* mean/std would give ~7+ here */
    assert(m.base_mean > -47 && m.base_mean < -43);

    /* 2. No false alarms on a still empty room for 60 s. */
    assert(feed(&m, &t, 600, -45, 2.0f) <= 6);          /* <= 1% of samples */

    /* 3. Walking through (large swings) is caught within ~1 s. */
    feed(&m, &t, 60, -45, 2.0f);                        /* make sure we start clear */
    int lat = latency(&m, &t, 30, -45, 8.0f);
    printf("walk detected after %d samples\n", lat);
    assert(lat > 0 && lat <= 10);

    /* 4. Clears after the hold time once the path is empty again. */
    feed(&m, &t, 40, -45, 2.0f);
    assert(m.state == MOTION_IDLE);

    /* 5. A still object that shifts the level by 4 dB is caught and stays flagged. */
    lat = latency(&m, &t, 30, -49, 2.0f);
    printf("4 dB shift detected after %d samples\n", lat);
    assert(lat > 0 && lat <= 12);
    assert(feed(&m, &t, 100, -49, 2.0f) >= 90);         /* still flagged while it stays */

    /* 6. And it clears once removed. */
    feed(&m, &t, 40, -45, 2.0f);
    assert(m.state == MOTION_IDLE);

    /* 7. Bad configuration is clamped, not trusted. */
    motion_cfg_t bad = { .window = 1000, .calib_samples = 100000, .k_sigma = 4, .hold_ms = 0 };
    motion_init(&m, &bad);
    assert(m.cfg.window == MOTION_MAX_WINDOW && m.cfg.calib_samples == MOTION_MAX_CALIB);
    bad.window = 0; bad.calib_samples = 0;
    motion_init(&m, &bad);
    assert(m.cfg.window == MOTION_FAST && m.cfg.calib_samples == 5);

    puts("motion tests passed");
    return 0;
}
