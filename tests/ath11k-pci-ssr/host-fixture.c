#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#define ATH11K_FLAG_UNREGISTERING 0
#define ATH11K_DBG_BOOT 0
#define ath11k_dbg(...) ((void)0)
#define ath11k_warn(...) ((void)0)
enum mhi_callback { MHI_CB_SYS_ERROR, MHI_CB_EE_RDDM, MHI_CB_EE_SBL_MODE, MHI_CB_OTHER };
struct work_struct { bool pending, running; };
struct ath11k_pci { enum mhi_callback mhi_pre_cb; };
struct ath11k_base {
    unsigned long dev_flags;
    pthread_mutex_t base_lock;
    void *workqueue_aux;
    struct work_struct reset_work, dump_work;
    struct ath11k_pci pci;
};
struct device { struct ath11k_base *ab; };
struct pci_dev { struct ath11k_base *ab; };
struct mhi_controller { struct device *cntrl_dev; };
static struct ath11k_base ab = { .base_lock = PTHREAD_MUTEX_INITIALIZER };
static struct device device = { &ab };
static struct pci_dev pdev = { &ab };
static struct mhi_controller controller = { &device };
static pthread_mutex_t state_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
enum role { MAIN, CALLBACK, SHUTDOWN };
static _Thread_local enum role role;
static _Thread_local bool owns_base;
static bool pause_admission, callback_paused, resume_callback;
static bool shutdown_blocked, shutdown_done, work_waiting, powered_down;
static unsigned late_queues, unsafe_powerdowns, api_errors, hint_calls, qrtr_calls;
static unsigned checks, failures;
static uint64_t normal_signature;
static void check(bool ok) { checks++; if (!ok) failures++; }
static void wait_changed(void)
{
    struct timespec deadline;
    clock_gettime(CLOCK_REALTIME, &deadline);
    deadline.tv_sec += 8;
    if (pthread_cond_timedwait(&changed, &state_lock, &deadline)) {
        fputs("host schedule timed out\n", stderr);
        exit(90);
    }
}
static __attribute__((unused)) void host_lock(pthread_mutex_t *lock)
{
    int ret = pthread_mutex_trylock(lock);
    if (ret == EBUSY) {
        if (role == SHUTDOWN) {
            pthread_mutex_lock(&state_lock);
            shutdown_blocked = true;
            pthread_cond_broadcast(&changed);
            pthread_mutex_unlock(&state_lock);
        }
        ret = pthread_mutex_lock(lock);
    }
    if (ret) exit(91);
    owns_base = true;
}
static __attribute__((unused)) void host_unlock(pthread_mutex_t *lock)
{
    owns_base = false;
    if (pthread_mutex_unlock(lock)) exit(92);
}
static bool host_test_bit(int bit, unsigned long *flags)
{
    bool value = !!(__atomic_load_n(flags, __ATOMIC_SEQ_CST) & (1UL << bit));
    if (role == CALLBACK && pause_admission) {
        pthread_mutex_lock(&state_lock);
        callback_paused = true;
        pthread_cond_broadcast(&changed);
        while (!resume_callback) wait_changed();
        pthread_mutex_unlock(&state_lock);
    }
    return value;
}
static __attribute__((unused)) void host_set_bit(int bit, unsigned long *flags)
{
    if (role == SHUTDOWN && !owns_base) {
        pthread_mutex_lock(&state_lock);
        api_errors++;
        pthread_mutex_unlock(&state_lock);
    }
    __atomic_fetch_or(flags, 1UL << bit, __ATOMIC_SEQ_CST);
}
#define spin_lock_bh(lock) host_lock(lock)
#define spin_unlock_bh(lock) host_unlock(lock)
#define test_bit(bit, flags) host_test_bit(bit, flags)
#define set_bit(bit, flags) host_set_bit(bit, flags)
static struct ath11k_base *dev_get_drvdata(struct device *dev) { return dev->ab; }
static struct ath11k_base *pci_get_drvdata(struct pci_dev *dev) { return dev->ab; }
static struct ath11k_pci *ath11k_pci_priv(struct ath11k_base *a) { return &a->pci; }
static bool queue_work(void *queue, struct work_struct *work)
{
    pthread_mutex_lock(&state_lock);
    if (queue != &ab) api_errors++;
    if (powered_down) late_queues++;
    bool queued = !work->pending;
    work->pending = true;
    pthread_mutex_unlock(&state_lock);
    return queued;
}
static __attribute__((unused)) bool cancel_work_sync(struct work_struct *work)
{
    pthread_mutex_lock(&state_lock);
    if (owns_base) api_errors++;
    bool cancelled = work->pending;
    work->pending = false;
    while (work->running) {
        work_waiting = true;
        pthread_cond_broadcast(&changed);
        wait_changed();
    }
    pthread_mutex_unlock(&state_lock);
    return cancelled;
}
static void ath11k_pci_set_irq_affinity_hint(struct ath11k_pci *pci, void *mask)
{
    (void)pci; (void)mask;
    pthread_mutex_lock(&state_lock);
    hint_calls++;
    pthread_mutex_unlock(&state_lock);
}
static void ath11k_pci_power_down(struct ath11k_base *a, bool suspend)
{
    (void)suspend;
    pthread_mutex_lock(&state_lock);
    if (owns_base || a->reset_work.pending || a->reset_work.running ||
        a->dump_work.pending || a->dump_work.running) unsafe_powerdowns++;
    powered_down = true;
    pthread_mutex_unlock(&state_lock);
}
static void ath11k_mhi_qrtr_instance_set(struct mhi_controller *c) { (void)c; qrtr_calls++; }
HOST_DRIVER_FUNCTIONS
static void reset_case(void)
{
    __atomic_store_n(&ab.dev_flags, 0, __ATOMIC_SEQ_CST);
    ab.workqueue_aux = &ab;
    ab.reset_work = (struct work_struct){0};
    ab.dump_work = (struct work_struct){0};
    ab.pci.mhi_pre_cb = MHI_CB_OTHER;
    pause_admission = callback_paused = resume_callback = false;
    shutdown_blocked = shutdown_done = work_waiting = powered_down = false;
    late_queues = unsafe_powerdowns = api_errors = hint_calls = qrtr_calls = 0;
    role = MAIN;
}
static void *run_callback(void *arg)
{
    (void)arg; role = CALLBACK;
    ath11k_mhi_op_status_cb(&controller, MHI_CB_EE_RDDM);
    return NULL;
}
static void *run_shutdown(void *arg)
{
    (void)arg; role = SHUTDOWN;
    ath11k_pci_shutdown(&pdev);
    pthread_mutex_lock(&state_lock);
    shutdown_done = true;
    pthread_cond_broadcast(&changed);
    pthread_mutex_unlock(&state_lock);
    return NULL;
}
int main(void)
{
    for (int closed = 0; closed < 2; closed++)
    for (int previous = 0; previous < 2; previous++)
    for (int event = MHI_CB_SYS_ERROR; event <= MHI_CB_OTHER; event++) {
        reset_case();
        ab.dev_flags = closed;
        if (previous) ab.pci.mhi_pre_cb = MHI_CB_EE_RDDM;
        ath11k_mhi_op_status_cb(&controller, event);
        bool queued = event == MHI_CB_EE_RDDM && !closed && !previous;
        check(ab.reset_work.pending == queued);
        check(qrtr_calls == (unsigned)(event == MHI_CB_EE_SBL_MODE));
        normal_signature = normal_signature * 131 + ab.reset_work.pending + 3 * qrtr_calls + ab.pci.mhi_pre_cb;
    }
    for (int reset = 0; reset < 2; reset++)
    for (int dump = 0; dump < 2; dump++) {
        reset_case();
        ab.reset_work.pending = reset;
        ab.dump_work.pending = dump;
        run_shutdown(NULL);
        check(powered_down && hint_calls == 1);
        check(!unsafe_powerdowns && !api_errors);
        check(!ab.reset_work.pending && !ab.dump_work.pending);
        ath11k_mhi_op_status_cb(&controller, MHI_CB_EE_RDDM);
        check(!late_queues && !ab.reset_work.pending);
    }
    reset_case();
    pause_admission = true;
    pthread_t callback, shutdown;
    if (pthread_create(&callback, NULL, run_callback, NULL)) return 93;
    pthread_mutex_lock(&state_lock);
    while (!callback_paused) wait_changed();
    pthread_mutex_unlock(&state_lock);
    if (pthread_create(&shutdown, NULL, run_shutdown, NULL)) return 94;
    pthread_mutex_lock(&state_lock);
    while (!shutdown_blocked && !shutdown_done) wait_changed();
    resume_callback = true;
    pthread_cond_broadcast(&changed);
    pthread_mutex_unlock(&state_lock);
    pthread_join(callback, NULL); pthread_join(shutdown, NULL);
    check(!late_queues && !unsafe_powerdowns && !api_errors);
    check(!ab.reset_work.pending && powered_down);
    for (int kind = 0; kind < 2; kind++) {
        reset_case();
        struct work_struct *active = kind ? &ab.dump_work : &ab.reset_work;
        active->running = true;
        if (pthread_create(&shutdown, NULL, run_shutdown, NULL)) return 95;
        pthread_mutex_lock(&state_lock);
        while (!work_waiting && !shutdown_done) wait_changed();
        check(!powered_down);
        active->running = false;
        pthread_cond_broadcast(&changed);
        pthread_mutex_unlock(&state_lock);
        pthread_join(shutdown, NULL);
        check(!unsafe_powerdowns && !api_errors && powered_down);
    }
    printf("{\"checks\":%u,\"failures\":%u,\"normal_signature\":\"%llu\","
           "\"linux_workqueue_modeled\":true,\"pthread_scheduling\":true}\n",
           checks, failures, (unsigned long long)normal_signature);
    return failures ? 1 : 0;
}
