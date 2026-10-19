#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define ATH11K_FLAG_CE_IRQ_ENABLED 0
#define ATH11K_FLAG_CRASH_FLUSH 1
#define ATH11K_FLAG_RECOVERY 2
#define ATH11K_FLAG_DEVICE_INIT_DONE 3
#define ATH11K_CE_RX_POST_RETRY_JIFFIES 10
#define TARGET_NUM_VDEVS(ab) 4
#define test_bit(n, p) (!!(*(p) & (1UL << (n))))
#define set_bit(n, p) (*(p) |= 1UL << (n))
#define clear_bit(n, p) (*(p) &= ~(1UL << (n)))
#define timer_container_of(p, t, m) ((struct ath11k_base *)((char *)(t) - offsetof(struct ath11k_base, m)))
#define ath11k_warn(...) ((void)0)
struct timer_list { bool pending, running, shutdown; };
struct ath11k_base;
struct ath11k_ce_pipe { struct ath11k_base *ab; bool live; int id; };
struct ath11k_base {
    struct { int ce_count; } hw_params;
    struct { struct ath11k_ce_pipe ce_pipe[12]; } ce;
    struct timer_list rx_replenish_retry;
    struct { bool enabled; } nss;
    unsigned long dev_flags;
    bool is_reset;
    int core_lock, num_radios;
    uint64_t free_vdev_map;
};
static unsigned checks, failures, unsafe, deletes, posts, cleanups, shadow_stops;
static unsigned irq_stops, ext_stops, hal_clears, ready_calls, blocked_rearms;
static unsigned callback_drains;
static bool irq_live, ext_live, inject_at_shadow, pcic_bus;
static int post_error, ready_error, nss_offload = 1;
static unsigned long jiffies;
static void ath11k_ce_rx_post_buf(struct ath11k_base *ab);
static void ath11k_ce_rx_replenish_retry(struct timer_list *t);
static void ath11k_ce_cleanup_pipes(struct ath11k_base *ab);
static void ath11k_ahb_stop(struct ath11k_base *ab);
void ath11k_pcic_stop(struct ath11k_base *ab);
static void check(bool ok) { checks++; if (!ok) failures++; }
static void mod_timer(struct timer_list *t, unsigned long expires)
{
    (void)expires;
    if (t->shutdown) blocked_rearms++;
    else t->pending = true;
}
static int timer_delete_sync(struct timer_list *t)
{
    bool pending = t->pending;
    deletes++;
    if (t->running) {
        /* API boundary model: the in-flight callback finishes before return. */
        t->running = false;
        callback_drains++;
        ath11k_ce_rx_replenish_retry(t);
    }
    t->pending = false;
    return pending;
}
static int timer_shutdown_sync(struct timer_list *t)
{
    t->shutdown = true;
    return timer_delete_sync(t);
}
static void fire(struct timer_list *t)
{
    if (!t->pending) return;
    t->pending = false;
    t->running = true;
    ath11k_ce_rx_replenish_retry(t);
    t->running = false;
}
static int ath11k_ce_rx_post_pipe(struct ath11k_ce_pipe *p)
{
    posts++;
    if (!p->live) unsafe++;
    return post_error;
}
static void ath11k_ce_stop_shadow_timers(struct ath11k_base *ab)
{
    shadow_stops++;
    if (inject_at_shadow) fire(&ab->rx_replenish_retry);
}
static void ath11k_ce_rx_pipe_cleanup(struct ath11k_ce_pipe *p)
{
    if (irq_live || p->ab->rx_replenish_retry.pending || p->ab->rx_replenish_retry.running)
        unsafe++;
    cleanups++;
    p->live = false;
}
static void ath11k_ce_poll_send_completed(struct ath11k_base *ab, int i)
{ (void)ab; (void)i; }
static void stop_irqs(struct ath11k_base *ab)
{ irq_live = false; irq_stops++; clear_bit(ATH11K_FLAG_CE_IRQ_ENABLED, &ab->dev_flags); }
static void ath11k_ahb_ce_irq_disable_sync(struct ath11k_base *ab) { stop_irqs(ab); }
static void ath11k_pcic_ce_irq_disable_sync(struct ath11k_base *ab) { stop_irqs(ab); }
static void ath11k_ahb_ce_irqs_enable(struct ath11k_base *ab)
{ irq_live = true; set_bit(ATH11K_FLAG_CE_IRQ_ENABLED, &ab->dev_flags); }
static void ath11k_pcic_ce_irqs_enable(struct ath11k_base *ab) { ath11k_ahb_ce_irqs_enable(ab); }
static void ath11k_hif_ce_irq_disable(struct ath11k_base *ab) { stop_irqs(ab); }
static void ath11k_hif_irq_disable(struct ath11k_base *ab)
{ (void)ab; ext_live = false; ext_stops++; }
static void mutex_lock(int *p) { if ((*p)++) unsafe++; }
static void mutex_unlock(int *p) { if (--(*p)) unsafe++; }
static void ath11k_nss_teardown(struct ath11k_base *ab) { (void)ab; }
static void ath11k_thermal_unregister(struct ath11k_base *ab) { (void)ab; }
static void ath11k_dp_pdev_free(struct ath11k_base *ab) { (void)ab; }
static void ath11k_spectral_deinit(struct ath11k_base *ab) { (void)ab; }
static void ath11k_wmi_detach(struct ath11k_base *ab) { (void)ab; }
static void ath11k_dp_pdev_reo_cleanup(struct ath11k_base *ab) { (void)ab; }
static void ath11k_dp_free(struct ath11k_base *ab) { (void)ab; }
static void ath11k_hal_srng_clear(struct ath11k_base *ab)
{
    if (irq_live || ext_live || ab->rx_replenish_retry.pending || ab->rx_replenish_retry.running)
        unsafe++;
    hal_clears++;
}
static void ath11k_hal_srng_deinit(struct ath11k_base *ab)
{ ath11k_hal_srng_clear(ab); }
static int ath11k_core_qmi_firmware_ready(struct ath11k_base *ab)
{ (void)ab; ready_calls++; return ready_error; }
static void reset(struct ath11k_base *ab, int count)
{
    memset(ab, 0, sizeof(*ab));
    ab->hw_params.ce_count = count;
    ab->num_radios = 3;
    ab->nss.enabled = true;
    for (int i = 0; i < count; i++)
        ab->ce.ce_pipe[i] = (struct ath11k_ce_pipe){ .ab = ab, .live = true, .id = i };
    unsafe = deletes = posts = cleanups = shadow_stops = 0;
    irq_stops = ext_stops = hal_clears = ready_calls = blocked_rearms = callback_drains = 0;
    irq_live = ext_live = inject_at_shadow = false;
    post_error = -EIO;
    ready_error = 0;
}

HOST_DRIVER_FUNCTIONS

int main(void)
{
    struct ath11k_base ab;
    unsigned scenarios = 0;
    unsigned native_signatures[36][7], native_count = 0;
    for (int count = 1; count <= 12; count++)
    for (int bus = 0; bus < 2; bus++)
    for (int state = 0; state < 3; state++) {
        reset(&ab, count);
        pcic_bus = bus;
        irq_live = true;
        ab.rx_replenish_retry.pending = state == 1;
        ab.rx_replenish_retry.running = state == 2;
        inject_at_shadow = true;
        if (pcic_bus) ath11k_pcic_stop(&ab); else ath11k_ahb_stop(&ab);
        check(!unsafe);
        check(!ab.rx_replenish_retry.pending && !ab.rx_replenish_retry.running);
        check(cleanups == (unsigned)count && shadow_stops == 1 && irq_stops == 1);
        check(deletes == 1 && !ab.rx_replenish_retry.shutdown);
        check(callback_drains == (unsigned)(state == 2));
        check(posts == (unsigned)(state == 2));
        unsigned before = posts;
        fire(&ab.rx_replenish_retry);
        check(posts == before && !unsafe);
        if (!pcic_bus) {
            unsigned signature[] = { deletes, shadow_stops, irq_stops, cleanups,
                                     posts, unsafe, callback_drains };
            memcpy(native_signatures[native_count++], signature, sizeof(signature));
        }
        /* Recovery keeps the timer reusable; no timer_setup() occurs again. */
        for (int i = 0; i < count; i++) ab.ce.ce_pipe[i].live = true;
        check(!(pcic_bus ? ath11k_pcic_start(&ab) : ath11k_ahb_start(&ab)));
        check(ab.rx_replenish_retry.pending && !blocked_rearms && irq_live);
        post_error = 0;
        fire(&ab.rx_replenish_retry);
        check(!ab.rx_replenish_retry.pending && !unsafe);
        if (pcic_bus) ath11k_pcic_stop(&ab); else ath11k_ahb_stop(&ab);
        check(!unsafe && !irq_live);
        scenarios++;
    }
    for (int count = 1; count <= 12; count++)
    for (int controlled = 0; controlled < 2; controlled++)
    for (int failed_ready = 0; failed_ready < 2; failed_ready++)
    for (int state = 0; state < 3; state++) {
        reset(&ab, count);
        ab.is_reset = controlled;
        irq_live = ext_live = !controlled;
        if (irq_live) set_bit(ATH11K_FLAG_CE_IRQ_ENABLED, &ab.dev_flags);
        set_bit(ATH11K_FLAG_RECOVERY, &ab.dev_flags);
        ab.rx_replenish_retry.pending = state == 1;
        ab.rx_replenish_retry.running = state == 2;
        inject_at_shadow = true;
        ready_error = failed_ready ? -EIO : 0;
        check(ath11k_core_reconfigure_on_crash(&ab) == ready_error);
        check(!unsafe && !irq_live && !ext_live && !ab.core_lock);
        check(!ab.rx_replenish_retry.pending && !ab.rx_replenish_retry.running);
        check(hal_clears == (unsigned)(failed_ready ? 2 : 1) && ready_calls == 1);
        check(deletes == 1 && !ab.rx_replenish_retry.shutdown);
        check(irq_stops == (unsigned)!controlled && ext_stops == (unsigned)!controlled);
        check(ab.nss.enabled == (bool)nss_offload);
        scenarios++;
    }
    /* Normal posting and ENOSPC must not gain cleanup-side policy changes. */
    for (int error = 0; error < 2; error++) {
        reset(&ab, 12);
        post_error = error ? -ENOSPC : 0;
        ath11k_ce_rx_post_buf(&ab);
        check(posts == 12 && !ab.rx_replenish_retry.pending && !deletes && !unsafe);
        scenarios++;
    }
    printf("{\"checks\":%u,\"failures\":%u,\"scenarios\":%u,\"native_signatures\":[", checks, failures, scenarios);
    for (unsigned i = 0; i < native_count; i++) {
        printf("%s[", i ? "," : "");
        for (unsigned j = 0; j < 7; j++) printf("%s%u", j ? "," : "", native_signatures[i][j]);
        printf("]");
    }
    puts("]}");
    return failures ? 1 : 0;
}
