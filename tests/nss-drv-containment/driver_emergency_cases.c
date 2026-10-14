/* Actual emergency poll and cleanup functions run against returning/blocked
 * host notifier APIs. No real firmware/crash/panic API is invoked. The fixture
 * active flag is an ownership substitute, not target NAPI scheduling proof. */
static void emergency_wait_event(enum host_api_event event) {
    assert(pthread_mutex_lock(&rendezvous)==0);
    while(event_index(event,0)<0) assert(pthread_cond_wait(&rendezvous_cond,&rendezvous)==0);
    assert(!writer_done); assert(pthread_mutex_unlock(&rendezvous)==0);
}
static void emergency_release_phase(bool tail) {
    struct napi_struct *napi=&nss_top_main.nss[0].int_ctx[0].napi;
    assert(pthread_mutex_lock(&napi->lock)==0);
    if(tail) napi->tail_active=false; else napi->active=false;
    assert(pthread_cond_broadcast(&napi->cond)==0); assert(pthread_mutex_unlock(&napi->lock)==0);
}
static void *emergency_cleanup_thread(void *unused) {
    (void)unused; nss_hal_clean_up_irq(&nss_top_main.nss[0].int_ctx[0]);
    assert(pthread_mutex_lock(&rendezvous)==0); writer_done=true;
    assert(pthread_cond_broadcast(&rendezvous_cond)==0); assert(pthread_mutex_unlock(&rendezvous)==0); return NULL;
}
static void *emergency_poll_thread(void *unused) {
    (void)unused; assert(nss_core_handle_napi_emergency(&nss_top_main.nss[0].int_ctx[0].napi,64)==0); return NULL;
}
static void host_emergency_legacy_controls(void) {
    setup(); struct int_ctx_instance *irq=&nss_top_main.nss[0].int_ctx[0]; irq->napi.active=true;
    assert(nss_core_handle_napi_emergency(&irq->napi,64)==0);
    assert(notify_calls==1 && host_napi_complete_calls==0 && irq->napi.active && irq->irq==100 && host_irq_rearm_calls==0);
    passed("legacy_emergency_returning_host_notify_leaves_ownership_defect_control");
    pthread_t writer; assert(pthread_create(&writer,NULL,emergency_cleanup_thread,NULL)==0);
    emergency_wait_event(HOST_NAPI_WAIT);
    assert(irq->irq==100 && event_index(HOST_IRQ_FREE,0)<0 && event_index(HOST_NAPI_GRACE,0)<0);
    /* Release the fixture artificially ONLY to make this defect control end.
     * The actual legacy poll did not release ownership. This is not a fix. */
    emergency_release_phase(false); assert(pthread_join(writer,NULL)==0);
    assert(host_napi_complete_calls==0 && !irq->irq);
    passed("legacy_emergency_cleanup_waits_until_artificial_fixture_release_defect_control");
}
static void host_emergency_ipq_cases(void) {
    setup(); struct int_ctx_instance *irq=&nss_top_main.nss[0].int_ctx[0]; irq->napi.active=true;
    assert(nss_core_handle_napi_emergency(&irq->napi,64)==0);
    assert(notify_calls==1 && host_napi_complete_calls==1 && !irq->napi.active && irq->irq==100 && host_irq_rearm_calls==0);
    assert(event_index(HOST_NAPI_COMPLETE,0)>event_index(HOST_NOTIFY_RETURN,0));
    nss_hal_clean_up_irq(irq); assert(!irq->irq && irq->napi.deleted);
    passed("candidate_emergency_returning_host_notify_completes_ownership_without_irq_rearm");
    setup(); irq=&nss_top_main.nss[0].int_ctx[0]; irq->napi.active=true; hold_notify=true;
    pthread_t poll,writer; assert(pthread_create(&poll,NULL,emergency_poll_thread,NULL)==0);
    assert(pthread_mutex_lock(&rendezvous)==0);
    while(!notify_entered) assert(pthread_cond_wait(&rendezvous_cond,&rendezvous)==0);
    assert(pthread_mutex_unlock(&rendezvous)==0);
    assert(pthread_create(&writer,NULL,emergency_cleanup_thread,NULL)==0); emergency_wait_event(HOST_NAPI_WAIT);
    assert(irq->irq==100 && host_napi_complete_calls==0 && event_index(HOST_IRQ_FREE,0)<0);
    assert(pthread_mutex_lock(&rendezvous)==0); release_notify=true;
    assert(pthread_cond_broadcast(&rendezvous_cond)==0); assert(pthread_mutex_unlock(&rendezvous)==0);
    assert(pthread_join(poll,NULL)==0 && pthread_join(writer,NULL)==0);
    assert(host_napi_complete_calls==1 && !irq->irq && host_irq_rearm_calls==0);
    passed("candidate_emergency_cleanup_waits_for_inflight_host_notify_then_actual_completion");
    setup(); irq=&nss_top_main.nss[0].int_ctx[0]; irq->napi.active=irq->napi.tail_active=true;
    assert(nss_core_handle_napi_emergency(&irq->napi,64)==0);
    assert(pthread_create(&writer,NULL,emergency_cleanup_thread,NULL)==0); emergency_wait_event(HOST_NAPI_GRACE);
    assert(irq->irq==100 && host_napi_complete_calls==1 && event_index(HOST_IRQ_FREE,0)<0);
    emergency_release_phase(true); assert(pthread_join(writer,NULL)==0);
    assert(!irq->irq && event_index(HOST_IRQ_FREE,0)>event_index(HOST_NAPI_GRACE,0) && host_irq_rearm_calls==0);
    passed("candidate_emergency_postcomplete_mock_tail_grace_precedes_irq_free");
}
