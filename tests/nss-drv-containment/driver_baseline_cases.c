/* Original defects are asserted as baseline controls, never repaired PASS. */
int main(void) {
    setup(); assert(nss_data_plane_register_to_nss_dp(&nss_top_main.nss[0],1));
    struct nss_data_plane_param before=nss_data_plane_params[1]; override_result=-EBUSY;
    assert(!nss_data_plane_register_to_nss_dp(&nss_top_main.nss[1],1));
    assert(nss_data_plane_params[1].nss_ctx!=before.nss_ctx && override_calls==2);
    passed("baseline_duplicate_registration_mutates_ndpp_before_rejection_control");
    setup(); assert(nss_data_plane_register_to_nss_dp(&nss_top_main.nss[0],1));
    assert(!port.host_admin_up && start_calls==0);
    passed("baseline_down_registration_skips_readiness_control");
    setup(); assert(nss_data_plane_register_to_nss_dp(&nss_top_main.nss[0],1));
    struct platform_device device={.id=0}; assert(nss_hal_remove(&device)==0);
    assert(nss_top_main.nss[1].int_ctx[0].irq==101 && !nss_top_main.nss[1].subsys_dp_register[1].ndev);
    passed("baseline_remove_clears_other_core_registry_before_other_irq_cleanup_control");
    setup(); nss_hal_clean_up_irq(&nss_top_main.nss[0].int_ctx[0]);
    assert(event_index(HOST_IRQ_FREE,0)>=0 && event_index(HOST_IRQ_FREE,0)<event_index(HOST_NAPI_GRACE,0));
    passed("baseline_irq_cleanup_frees_before_napi_del_grace_control");
    setup(); assert(nss_data_plane_init_delay_work()==0); assert(nss_data_plane_schedule_registration());
    assert(nss_hal_remove(&device)==0); assert(override_calls==0);
    nss_data_plane_destroy_delay_work();
    assert(override_calls==1 && nss_top_main.nss[0].int_ctx[0].irq==0 && nss_top_main.nss[0].subsys_dp_register[1].ndev==&port);
    passed("baseline_work_destroy_flushes_queued_registration_after_irq_cleanup_control");
    host_emergency_legacy_controls();
    return 0;
}
