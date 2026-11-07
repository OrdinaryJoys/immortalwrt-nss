#ifdef HOST_CONTROL_GROUP
static void host_controls_assert_receive_live(void) {
    assert(!nss_hal_receive_group_stopped);
    for(int core=0;core<NSS_MAX_CORES;core++) {
        struct nss_ctx_instance *ctx=&nss_top_main.nss[core];
        assert(ctx->napi_ndev==&napi_devices[core] && !napi_devices[core].host_frees);
        assert(ctx->int_ctx[0].irq==(unsigned)(100+core));
        assert(ctx->int_ctx[0].napi.enabled && !ctx->int_ctx[0].napi.deleted);
        assert(event_index(HOST_NAPI_WAIT,core)<0 && event_index(HOST_IRQ_FREE,core)<0);
    }
}

static void host_controls_assert_drained(void);
static void *host_controls_stop_thread(void *unused) {
    (void)unused; nss_hal_quiesce_control_group(); host_controls_assert_drained();
    assert(pthread_mutex_lock(&rendezvous)==0); writer_done=true;
    assert(pthread_cond_broadcast(&rendezvous_cond)==0);
    assert(pthread_mutex_unlock(&rendezvous)==0); return NULL;
}

static void host_controls_release_held(int kind) {
    assert(pthread_mutex_lock(&rendezvous)==0);
    while(event_index(HOST_CONTROL_CLOSE,kind)<0)
        assert(pthread_cond_wait(&rendezvous_cond,&rendezvous)==0);
    assert(!writer_done && event_index(HOST_CONTROL_DRAINED,kind)<0);
    assert(pthread_mutex_unlock(&rendezvous)==0);
    assert(!host_control_begin(kind)); host_controls_assert_receive_live();
    host_control_end(kind);
}

static void host_controls_assert_drained(void) {
    assert(nss_hal_control_group_stopped);
    assert(pthread_mutex_lock(&host_control_lock)==0);
    for(int kind=0;kind<HOST_CONTROL_COUNT;kind++)
        assert(!host_controls[kind].accepting && !host_controls[kind].active && host_controls[kind].stops==1);
    assert(pthread_mutex_unlock(&host_control_lock)==0);
}
static void host_controls_assert_before_receive(void) {
    for(int kind=0;kind<HOST_CONTROL_COUNT;kind++) {
        int closed=event_index(HOST_CONTROL_CLOSE,kind);
        int joined=event_index(HOST_CONTROL_DRAINED,kind);
        assert(closed>=0 && joined>closed);
        if(kind) assert(closed>event_index(HOST_CONTROL_DRAINED,kind-1));
        for(int core=0;core<NSS_MAX_CORES;core++)
            assert(event_index(HOST_NAPI_WAIT,core)>joined);
    }
}
#endif
