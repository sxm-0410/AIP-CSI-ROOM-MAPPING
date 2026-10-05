#include "motion.h"
#include <math.h>
#include <string.h>

/* Median, sorting v in place (insertion sort; n <= MOTION_MAX_CALIB). */
static float median_of(float *v, int n)
{
    for (int i = 1; i < n; i++) {
        float x = v[i];
        int j = i - 1;
        while (j >= 0 && v[j] > x) { v[j + 1] = v[j]; j--; }
        v[j + 1] = x;
    }
    return n % 2 ? v[n / 2] : 0.5f * (v[n / 2 - 1] + v[n / 2]);
}

/* median + k * 1.4826 * MAD. Unlike mean/std, this ignores a burst of movement (up to
 * ~half the samples) during learning, so one bad moment cannot wreck the limit. */
static float robust_limit(const float *src, int n, float k, float *median_out)
{
    float tmp[MOTION_MAX_CALIB];
    memcpy(tmp, src, n * sizeof(float));
    float med = median_of(tmp, n);
    for (int i = 0; i < n; i++) tmp[i] = fabsf(src[i] - med);
    float mad = median_of(tmp, n);
    *median_out = med;
    return med + k * 1.4826f * mad;
}

void motion_init(motion_t *m, const motion_cfg_t *cfg)
{
    memset(m, 0, sizeof(*m));
    m->cfg = *cfg;
    if (m->cfg.window < MOTION_FAST) m->cfg.window = MOTION_FAST;
    if (m->cfg.window > MOTION_MAX_WINDOW) m->cfg.window = MOTION_MAX_WINDOW;
    if (m->cfg.calib_samples < 5) m->cfg.calib_samples = 5;
    if (m->cfg.calib_samples > MOTION_MAX_CALIB) m->cfg.calib_samples = MOTION_MAX_CALIB;
    m->state = MOTION_CALIBRATING;
}

int motion_progress_pct(const motion_t *m)
{
    return m->state == MOTION_CALIBRATING ? 100 * m->calib_seen / m->cfg.calib_samples : 100;
}

/* Learn from the quietest MOTION_QUIET_PCT % of the learning windows only, so a person
 * walking by (which taints every window that overlaps it) cannot inflate the limits. */
static void finish_calibration(motion_t *m)
{
    int n = m->calib_seen;
    float tmp[MOTION_MAX_CALIB], med;

    memcpy(tmp, m->std_hist, n * sizeof(float));
    median_of(tmp, n);                                     /* sorts tmp */
    float cut = tmp[n * MOTION_QUIET_PCT / 100 - 1];
    int q = 0;
    for (int i = 0; i < n; i++) {                          /* compact in place: q <= i */
        if (m->std_hist[i] > cut) continue;
        m->std_hist[q] = m->std_hist[i];
        m->mean_hist[q] = m->mean_hist[i];
        m->fast_hist[q] = m->fast_hist[i];
        q++;
    }
    n = q;

    memcpy(tmp, m->mean_hist, n * sizeof(float));
    m->base_mean = median_of(tmp, n);

    m->thr_std = robust_limit(m->std_hist, n, m->cfg.k_sigma, &med);
    if (m->thr_std < med + m->cfg.min_std_margin) m->thr_std = med + m->cfg.min_std_margin;
    if (m->thr_std < MOTION_STD_FLOOR_X * med)              /* must be clearly above normal */
        m->thr_std = MOTION_STD_FLOOR_X * med;

    for (int i = 0; i < n; i++) tmp[i] = fabsf(m->fast_hist[i] - m->base_mean);
    m->thr_level = robust_limit(tmp, n, m->cfg.k_sigma, &med);
    if (m->thr_level < m->cfg.level_shift_db) m->thr_level = m->cfg.level_shift_db;

    m->state = MOTION_IDLE;
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
    float fast = 0;                                /* newest MOTION_FAST samples: reacts quickly */
    for (int i = 1; i <= MOTION_FAST; i++) fast += m->buf[(m->head - i + w) % w];
    fast /= MOTION_FAST;

    m->last_std = (float)sqrt(var / w);
    m->last_mean = (float)mean;
    m->last_fast = fast;

    if (m->state == MOTION_CALIBRATING) {
        int i = m->calib_seen++;
        m->std_hist[i] = m->last_std;
        m->mean_hist[i] = m->last_mean;
        m->fast_hist[i] = fast;
        if (m->calib_seen >= m->cfg.calib_samples) finish_calibration(m);
        return m->state;
    }

    if (m->last_std > m->thr_std || fabsf(fast - m->base_mean) > m->thr_level)
        m->hold_until_ms = now_ms + m->cfg.hold_ms;
    m->state = now_ms < m->hold_until_ms ? MOTION_ACTIVE : MOTION_IDLE;
    return m->state;
}
