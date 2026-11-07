/* Observable API boundary substitutes, not real sysctl/producer retirement.
 * The actual HAL orchestrator must close and join each dependency in order.
 * Held host readers keep it blocked while actual receive resources stay live.
 */
#ifdef HOST_CONTROL_GROUP
enum host_control_kind { HOST_ROOT_CONTROL, HOST_FREQUENCY_CONTROL,
                         HOST_COREDUMP_CONTROL, HOST_CONTROL_COUNT };
static pthread_mutex_t host_control_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t host_control_cond=PTHREAD_COND_INITIALIZER;
static struct { bool accepting; unsigned active,stops; } host_controls[HOST_CONTROL_COUNT];

static void host_control_reset(void) {
    assert(pthread_mutex_lock(&host_control_lock)==0);
    for(int i=0;i<HOST_CONTROL_COUNT;i++) {
        assert(!host_controls[i].active);
        host_controls[i].accepting=true; host_controls[i].stops=0;
    }
    assert(pthread_mutex_unlock(&host_control_lock)==0);
}
static bool host_control_begin(int kind) {
    assert(kind>=0 && kind<HOST_CONTROL_COUNT);
    assert(pthread_mutex_lock(&host_control_lock)==0);
    bool accepted=host_controls[kind].accepting;
    if(accepted) host_controls[kind].active++;
    assert(pthread_mutex_unlock(&host_control_lock)==0);
    return accepted;
}
static void host_control_end(int kind) {
    assert(pthread_mutex_lock(&host_control_lock)==0);
    assert(host_controls[kind].active); host_controls[kind].active--;
    assert(pthread_cond_broadcast(&host_control_cond)==0);
    assert(pthread_mutex_unlock(&host_control_lock)==0);
}
static void host_control_stop(int kind) {
    assert(!host_holds_rtnl);
    assert(pthread_mutex_lock(&host_control_lock)==0);
    assert(host_controls[kind].stops++==0);
    if(kind) assert(!host_controls[kind-1].accepting && !host_controls[kind-1].active);
    host_controls[kind].accepting=false;
    host_observe(HOST_CONTROL_CLOSE,kind);
    while(host_controls[kind].active)
        assert(pthread_cond_wait(&host_control_cond,&host_control_lock)==0);
    host_observe(HOST_CONTROL_DRAINED,kind);
    assert(pthread_mutex_unlock(&host_control_lock)==0);
}
static void nss_root_controls_stop(void) { host_control_stop(HOST_ROOT_CONTROL); }
static void nss_freq_work_quiesce(void) { host_control_stop(HOST_FREQUENCY_CONTROL); }
static void nss_coredump_quiesce(void) { host_control_stop(HOST_COREDUMP_CONTROL); }
#endif
