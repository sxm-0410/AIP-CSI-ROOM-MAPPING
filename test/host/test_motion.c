/* Host test: cc -Imain test/host/test_motion.c main/motion.c -lm -o /tmp/tm && /tmp/tm */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "motion.h"

static float noise(float amp) { return ((rand() % 2001) - 1000) / 1000.0f * amp; }

int main(void)
{
    motion_cfg_t c = { .window = 20, .calib_samples = 100, .k_sigma = 4,
                       .min_std_margin = 0.5f, .level_shift_db = 4, .hold_ms = 2000 };
    motion_t m; motion_init(&m, &c);
    int64_t t = 0;
    for (int i = 0; i < 300; i++, t += 100) motion_update(&m, -45 + noise(0.8f), t);
    assert(m.state == MOTION_IDLE);                      /* calibrated, quiet */

    int false_alarms = 0;
    for (int i = 0; i < 300; i++, t += 100)
        false_alarms += motion_update(&m, -45 + noise(0.8f), t) == MOTION_ACTIVE;
    assert(false_alarms == 0);

    int hit = 0;                                         /* walking: big swings */
    for (int i = 0; i < 50; i++, t += 100)
        hit += motion_update(&m, -45 + noise(6.0f), t) == MOTION_ACTIVE;
    assert(hit > 30);

    for (int i = 0; i < 60; i++, t += 100) motion_update(&m, -45 + noise(0.8f), t);
    assert(m.state == MOTION_IDLE);                      /* clears after hold */

    int shift = 0;                                       /* standing in path: level drop */
    for (int i = 0; i < 60; i++, t += 100)
        shift += motion_update(&m, -53 + noise(0.8f), t) == MOTION_ACTIVE;
    assert(shift > 30);

    puts("motion tests passed");
    return 0;
}
