/* Per-case private-global reset creates a fresh host fixture module instance.
 * No production restart API or equivalent DRV state machine is implemented. */
static void candidate_setup(void) {
    setup();
    nss_data_plane_workqueue=NULL;
    nss_data_plane_registration_closing=false; nss_data_plane_work_initialized=false;
    nss_data_plane_ops_prepared=false; memset(nss_data_plane_hal_registered,0,sizeof(nss_data_plane_hal_registered));
    nss_hal_receive_group_closing=nss_hal_receive_group_stopped=false; memset(nss_hal_core_removed,0,sizeof(nss_hal_core_removed));
}
static bool register_port(int core) { rtnl_lock(); bool result=nss_data_plane_register_to_nss_dp(&nss_top_main.nss[core],1); rtnl_unlock(); return result; }
static void all_tables_present(void) {
    for(int core=0;core<NSS_MAX_CORES;core++) assert(nss_top_main.nss[core].subsys_dp_register[1].ndev==&port);
    assert(nss_data_plane_params[1].dpc.dev==&port && nss_data_plane_params[1].nss_ctx==&nss_top_main.nss[0]);
}
static void all_receive_retired(void) {
    assert(nss_hal_receive_group_stopped && nss_data_plane_registration_stopped());
    for(int core=0;core<NSS_MAX_CORES;core++) {
        for(int i=0;i<NSS_MAX_IRQ_PER_CORE;i++) assert(!nss_top_main.nss[core].int_ctx[i].irq);
        struct nss_subsystem_dataplane_register *reg=&nss_top_main.nss[core].subsys_dp_register[1];
        assert(!reg->ndev && !reg->cb && !reg->ext_cb && !reg->app_data && !reg->features && !reg->type);
    }
    assert(!nss_data_plane_params[1].nss_ctx && !nss_data_plane_params[1].dpc.dev && !nss_data_plane_params[1].features);
}
static void wait_event_seen(enum host_api_event event,int core) {
    assert(pthread_mutex_lock(&rendezvous)==0);
    while(event_index(event,core)<0) assert(pthread_cond_wait(&rendezvous_cond,&rendezvous)==0);
    assert(!writer_done); assert(pthread_mutex_unlock(&rendezvous)==0);
}
static void *remove_thread(void *argument) {
    struct platform_device dev={.id=(int)(intptr_t)argument}; assert(nss_hal_remove(&dev)==0);
    assert(pthread_mutex_lock(&rendezvous)==0); writer_done=true;
    assert(pthread_cond_broadcast(&rendezvous_cond)==0); assert(pthread_mutex_unlock(&rendezvous)==0); return NULL;
}
static void release_poll_phase(int core,bool tail) {
    struct napi_struct *napi=&nss_top_main.nss[core].int_ctx[0].napi;
    assert(pthread_mutex_lock(&napi->lock)==0);
    if(tail) napi->tail_active=false; else napi->active=false;
    assert(pthread_cond_broadcast(&napi->cond)==0); assert(pthread_mutex_unlock(&napi->lock)==0);
}
int main(void) {
    struct platform_device dev0={.id=0},dev1={.id=1};
    candidate_setup(); unsigned enqueues=host_queue.enqueue_calls;
    assert(!nss_data_plane_schedule_registration() && host_queue.enqueue_calls==enqueues);
    passed("candidate_preinit_enqueue_refused_before_kernel_queue_api");
    candidate_setup(); host_create_fail=true; assert(nss_data_plane_init_delay_work()==-ENOMEM);
    assert(!nss_data_plane_schedule_registration()); passed("candidate_workqueue_init_failure_never_publishes_queue");
    candidate_setup(); assert(nss_data_plane_init_delay_work()==0); struct workqueue_struct *queue=nss_data_plane_workqueue;
    assert(nss_data_plane_init_delay_work()==-EBUSY && nss_data_plane_workqueue==queue);
    nss_data_plane_destroy_delay_work(); passed("candidate_duplicate_workqueue_init_preserves_original_queue");
    candidate_setup(); assert(nss_data_plane_init_delay_work()==0); assert(nss_data_plane_schedule_registration());
    nss_data_plane_stop_registration(); assert(nss_data_plane_registration_stopped() && !host_queue.pending);
    enqueues=host_queue.enqueue_calls; assert(!nss_data_plane_schedule_registration() && host_queue.enqueue_calls==enqueues);
    assert(nss_data_plane_init_delay_work()==-ESHUTDOWN); nss_data_plane_destroy_delay_work(); nss_data_plane_destroy_delay_work();
    assert(!nss_data_plane_workqueue && host_queue.destroy_calls==1 && override_calls==0);
    passed("candidate_close_cancels_pending_refuses_enqueue_and_permanently_refuses_reinit");
    candidate_setup(); assert(register_port(0)); struct nss_data_plane_param saved=nss_data_plane_params[1];
    override_result=-EBUSY; assert(!register_port(1)); assert(!memcmp(&saved,&nss_data_plane_params[1],sizeof(saved)) && override_calls==1);
    all_tables_present(); passed("candidate_duplicate_registration_refused_before_ndpp_mutation_or_override");
    candidate_setup(); assert(register_port(0)); assert(start_calls==1 && !port.host_admin_up);
    passed("candidate_down_registration_commits_readiness_without_changing_admin_state");
    candidate_setup(); port.host_admin_up=true; assert(register_port(0)); assert(start_calls==1 && port.host_admin_up);
    passed("candidate_up_registration_commits_readiness_once");
    candidate_setup(); nss_data_plane_stop_registration(); saved=nss_data_plane_params[1];
    assert(!register_port(0) && !memcmp(&saved,&nss_data_plane_params[1],sizeof(saved)) && override_calls==0);
    passed("candidate_registration_after_close_refuses_before_ndpp_mutation");
    candidate_setup(); __nss_data_plane_register(&nss_top_main.nss[0]); __nss_data_plane_register(&nss_top_main.nss[1]); __nss_data_plane_register(&nss_top_main.nss[0]);
    assert(ops_prepare_calls==1 && hal_register_calls==2 && override_calls==1 && nss_data_plane_params[1].nss_ctx==&nss_top_main.nss[0]);
    passed("candidate_worker_wrapper_prepares_ops_and_soc_registration_once");
    candidate_setup(); assert(register_port(0)); rtnl_lock(); nss_data_plane_quarantine_registered(); rtnl_unlock();
    all_tables_present(); assert(restore_calls==1 && hal_unregister_calls==0 && nss_top_main.nss[0].int_ctx[0].irq==100 && nss_top_main.nss[1].int_ctx[0].irq==101);
    passed("candidate_dp_only_quarantine_retains_rx_registry_and_ndpp_until_receive_drain");
    candidate_setup(); assert(nss_data_plane_init_delay_work()==0); assert(nss_data_plane_schedule_registration());
    assert(nss_hal_remove(&dev0)==0); assert(override_calls==0 && !host_queue.pending); nss_data_plane_destroy_delay_work();
    all_receive_retired(); passed("candidate_remove_cancels_queued_registration_before_irq_cleanup");
    candidate_setup(); assert(nss_data_plane_init_delay_work()==0); hold_config=true; assert(nss_data_plane_schedule_registration());
    pthread_t worker,writer; assert(pthread_create(&worker,NULL,host_execute_queued_work,&host_queue)==0);
    assert(pthread_mutex_lock(&rendezvous)==0); while(!config_entered) assert(pthread_cond_wait(&rendezvous_cond,&rendezvous)==0); assert(pthread_mutex_unlock(&rendezvous)==0);
    assert(pthread_create(&writer,NULL,remove_thread,(void *)(intptr_t)0)==0); wait_event_seen(HOST_CANCEL_WAIT,-1);
    assert(nss_data_plane_registration_stopped()); enqueues=host_queue.enqueue_calls;
    assert(!nss_data_plane_schedule_registration() && host_queue.enqueue_calls==enqueues);
    assert(event_index(HOST_NAPI_WAIT,0)<0 && event_index(HOST_NAPI_WAIT,1)<0 && nss_top_main.nss[0].int_ctx[0].irq==100 && nss_top_main.nss[1].int_ctx[0].irq==101);
    assert(pthread_mutex_lock(&rendezvous)==0); release_config=true; assert(pthread_cond_broadcast(&rendezvous_cond)==0); assert(pthread_mutex_unlock(&rendezvous)==0);
    assert(pthread_join(worker,NULL)==0); assert(pthread_join(writer,NULL)==0); assert(!host_queue.running && override_calls==0);
    all_receive_retired(); nss_data_plane_destroy_delay_work(); passed("candidate_running_registration_ack_finishes_before_receive_cleanup_and_new_enqueue_refused");
    candidate_setup(); assert(register_port(0));
    for(int core=0;core<NSS_MAX_CORES;core++) { struct napi_struct *napi=&nss_top_main.nss[core].int_ctx[0].napi; napi->active=napi->tail_active=true; }
    assert(pthread_create(&writer,NULL,remove_thread,(void *)(intptr_t)0)==0);
    for(int core=0;core<NSS_MAX_CORES;core++) {
        wait_event_seen(HOST_NAPI_WAIT,core); all_tables_present(); assert(restore_calls==1);
        release_poll_phase(core,false); wait_event_seen(HOST_NAPI_GRACE,core); all_tables_present();
        assert(nss_top_main.nss[core].int_ctx[0].irq==(unsigned)(100+core) && event_index(HOST_IRQ_FREE,core)<0);
        release_poll_phase(core,true);
    }
    assert(pthread_join(writer,NULL)==0); all_receive_retired();
    for(int core=0;core<NSS_MAX_CORES;core++) assert(event_index(HOST_IRQ_FREE,core)>event_index(HOST_NAPI_GRACE,core));
    passed("candidate_all_mock_core_poll_and_tail_readers_drain_before_registry_clear_irq_retained_until_grace");
    candidate_setup(); assert(register_port(0)); assert(nss_hal_remove(&dev0)==0); assert(nss_hal_remove(&dev1)==0);
    unsigned restores=restore_calls,stats=stats_clean_calls; int event_total=event_count;
    assert(nss_hal_remove(&dev0)==0 && nss_hal_remove(&dev1)==0);
    assert(restore_calls==restores && stats_clean_calls==stats && event_count==event_total && napi_devices[0].host_frees==1 && napi_devices[1].host_frees==1);
    all_receive_retired(); passed("candidate_repeated_both_core_remove_idempotent_no_double_resource_retirement");
    candidate_setup(); struct platform_device invalid={.id=-1}; assert(nss_hal_remove(&invalid)==-EINVAL); invalid.id=NSS_MAX_CORES;
    assert(nss_hal_remove(&invalid)==-EINVAL && event_count==0 && stats_clean_calls==0);
    passed("candidate_remove_invalid_core_refused_before_resource_mutation");
    candidate_setup(); assert(nss_hal_probe(&dev0)==0 && probe_calls==1); assert(nss_hal_remove(&dev0)==0);
    assert(nss_hal_probe(&dev1)==-ESHUTDOWN && probe_calls==1); passed("candidate_late_public_probe_admission_refused_after_group_close");
    candidate_setup(); assert(register_port(0)); nss_top_main.num_nss=1; nss_top_main.nss[1].num_irq=0;
    nss_top_main.nss[1].int_ctx[1].irq=111; nss_top_main.nss[1].int_ctx[1].napi.enabled=true;
    assert(nss_hal_remove(&dev0)==0); all_receive_retired(); assert(nss_top_main.nss[1].int_ctx[1].napi.deleted);
    passed("candidate_all_max_core_irq_slots_drained_even_outside_reported_num_nss_num_irq");
    host_emergency_ipq_cases();
    return 0;
}
