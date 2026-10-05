#include "motion.h"
#include <math.h>
#include <string.h>

void motion_init(motion_t *m, const motion_cfg_t *cfg)
{
    memset(m, 0, sizeof(*m));
    m->cfg = *cfg;
    if (m->cfg.window < 2) m->cfg.window = 2;
    if (m->cfg.window > MOTION_MAX_WINDOW) m->cfg.window = MOTION_MAX_WINDOW;
    m->state = MOTION_CALIBRATING;
}

void motion_recalibrate(motion_t *m)
{
    motion_cfg_t c = m->cfg;
    motion_init(m, &c);
}

motion_state_t motion_update(motion_t *m, float rssi, int64_t now_ms)
{
    int w = m->cfg.window;
    m->buf[m->head] = rssi;
    m->head = (m->head + 1) % w;
    if (m->n < w) m->n++;
    if (m->n < w) return m->state;                 /* window not full yet */

    double mean = 0, var = 0;
    for (int i = 0; i < w; i++) mean += m->buf[i];
    mean /= w;
    for (int i = 0; i < w; i++) var += (m->buf[i] - mean) * (m->buf[i] - mean);
    float sd = (float)sqrt(var / w);
    m->last_std = sd;
    m->last_mean = (float)mean;

    if (m->state == MOTION_CALIBRATING) {
        m->sum_std += sd;
        m->sum_std2 += (double)sd * sd;
        m->sum_mean += mean;
        if (++m->calib_seen >= m->cfg.calib_samples) {
            double c = m->calib_seen;
            double ms = m->sum_std / c;
            double vs = m->sum_std2 / c - ms * ms;
            float sds = (float)sqrt(vs > 0 ? vs : 0);
            float margin = m->cfg.k_sigma * sds;
            if (margin < m->cfg.min_std_margin) margin = m->cfg.min_std_margin;
            m->thr_std = (float)ms + margin;
            m->base_mean = (float)(m->sum_mean / c);
            m->state = MOTION_IDLE;
        }
        return m->state;
    }

    if (sd > m->thr_std || fabsf((float)mean - m->base_mean) > m->cfg.level_shift_db)
        m->hold_until_ms = now_ms + m->cfg.hold_ms;
    m->state = now_ms < m->hold_until_ms ? MOTION_ACTIVE : MOTION_IDLE;
    return m->state;
}
