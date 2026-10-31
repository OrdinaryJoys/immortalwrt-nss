"""Actual complete-function directed mutations; runner owns fixed obligations."""

def once(text, before, after):
    if before == after or text.count(before) != 1:
        raise RuntimeError('one-changing-mutation-anchor')
    return text.replace(before, after, 1)


def variants(extracted, profile):
    bodies=extracted['bodies'];rows=[]
    aliases={'hppe_init':'actual_hppe_init','hppe_cleanup':'actual_hppe_cleanup','hsl_dev_init_core':'actual_hsl_core'}
    active=profile in ('hppe','kernel','user','combined')
    def add(name,symbol,before,after,case,marker,enabled=True):
        if not enabled:return
        original=bodies[symbol];changed=once(original,before,after)
        if symbol in aliases:
            original=original.replace(symbol,aliases[symbol],1);changed=changed.replace(symbol,aliases[symbol],1)
        rows.append(dict(name=name,symbol=symbol,before=original,after=changed,case=case,marker=marker,
                         classification='directed actual source semantic mutant'))
    add('public-api-bypass','hsl_api_init','rv = hsl_dev_api_init_check(dev_id);','rv = SW_OK;',
        'api-P','FIRST_ERROR')
    add('fal-unauthorized-api','fal_init','rv = hsl_dev_api_init_guarded(guard);','rv = hsl_api_init(dev_id);',
        'fal-hppe','FIRST_ERROR',active)
    add('fal-unauthorized-hsl','fal_init','rv = hsl_dev_init_guarded(guard);','rv = hsl_dev_init(dev_id, cfg);',
        'fal-hppe','FIRST_ERROR',active)
    add('port-residue-bypass','hsl_port_prop_slot_available',
        'return p_port_info[dev_id] ? SW_ALREADY_EXIST : SW_OK;','return SW_OK;',
        'api-P','FIRST_ERROR')
    add('ambient-busy-bypass','hsl_dev_init_available','return SW_BUSY;','return SW_OK;',
        'probe-APISET','REENTRY_BUSY',active)
    add('busy-silent-api-write','hsl_dev_api_init_check',
        'return hsl_dev_init_available(dev_id, NULL);',
        '#ifdef HPPE\n    if (dev_id < SW_MAX_NR_DEV && hsl_dev_guards[dev_id].phase != HSL_DEV_IDLE) { hsl_api_ptr_get(dev_id)->dev_clean = hppe_cleanup; }\n#endif\n    return hsl_dev_init_available(dev_id, NULL);',
        'probe-APISET','REENTRY_STATE_UNCHANGED',active)
    add('busy-silent-metadata-write','hsl_dev_init_available',
        'if (hsl_dev_guards[dev_id].phase != HSL_DEV_IDLE)\n        return SW_BUSY;',
        'if (hsl_dev_guards[dev_id].phase != HSL_DEV_IDLE) { dev_table[dev_id].cpu_port_nr ^= 1; return SW_BUSY; }',
        'probe-APISET','REENTRY_STATE_UNCHANGED',active)
    add('missing-child-query','hppe_init_state_check','return SW_ALREADY_EXIST;','return SW_OK;',
        'unowned','FIRST_ERROR',active)
    add('lower-child-init-query-omitted','hsl_dev_init_available','rv = hppe_init_state_check(dev_id);','rv = SW_OK;',
        'unowned-init-only','EXACT_STATE_TRACE',profile=='combined')
    add('adapter-gate-omitted','hsl_dev_init_available','if (adpt_api_ptr_get(dev_id))','if (0)',
        'adapter-residue','FIRST_ERROR',active)
    add('preclear-port-gate-omitted','hsl_dev_init_available','rv = hsl_port_prop_slot_available(dev_id);','rv = SW_OK;',
        'foreign-P','EXACT_STATE_TRACE',profile in ('hppe','kernel','user'))
    add('missing-acquisition-flag','hsl_dev_init_core','hsl_hppe_owned[dev_id] = A_TRUE;',
        'hsl_hppe_owned[dev_id] = A_FALSE;','fal-hppe','FIRST_ERROR',active)
    add('skip-owned-child-retirement','hsl_dev_cleanup_core','rv = hppe_cleanup_owned(dev_id, hsl_hppe_owner_epoch[dev_id]);','rv = SW_OK;',
        'fal-hppe','EXACT_STATE_TRACE',active)
    add('adopt-direct-child','hsl_dev_cleanup_core','rv = hppe_init_state_check(dev_id);','rv = SW_OK;',
        'unowned','FIRST_ERROR',active)
    add('adopt-serial-partial-child','hsl_dev_cleanup_core','rv = hppe_init_state_check(dev_id);','rv = SW_OK;',
        'partial-serial','FIRST_ERROR',active)
    add('adopt-sd-model-child','hsl_dev_cleanup_core','rv = hppe_init_state_check(dev_id);','rv = SW_OK;',
        'sd-direct-child','FIRST_ERROR',active)
    add('failed-clean-silent-old-token-write','hsl_port_prop_cleanup_owned',
        'if (!owner || p_port_info[dev_id] != owner)\n        return SW_BAD_STATE;',
        'if (!owner || p_port_info[dev_id] != owner) { if (owner) { owner->property[HSL_PP_CPU] ^= (1u << 7); } return SW_BAD_STATE; }',
        'cleanup-mismatch','EXACT_STATE_TRACE',profile in ('hppe','kernel','user'))
    add('fal-release-before-adapter','fal_init','rv = adpt_init(dev_id, cfg);',
        'hsl_dev_guard_end(&guard); rv = adpt_init(dev_id, cfg);','probe-ADPT','REENTRY_BUSY',active)
    add('fal-release-before-vlan','fal_init','rv = fal_vlan_init(dev_id);',
        'hsl_dev_guard_end(&guard); rv = fal_vlan_init(dev_id);','probe-VLAN_INIT-error','REENTRY_BUSY',active)
    add('fal-release-before-vlan-clean','fal_cleanup','rv = fal_vlan_cleanup(dev_id);',
        'hsl_dev_guard_end(&guard); rv = fal_vlan_cleanup(dev_id);','probe-VLAN_CLEAN','REENTRY_BUSY',active)
    add('cleanup-release-before-uk','hsl_dev_cleanup_guarded','guard->phase = HSL_DEV_CLEAN_RUNNING;',
        'guard->phase = HSL_DEV_IDLE;','probe-UK_CLEAN','REENTRY_BUSY',active)
    for name,expression,case in (
        ('sd-repeated','sd_init(dev_id,cfg)','fault-SD'),
        ('uk-init-repeated','sw_uk_init(cfg->nl_prot)','fault-UK_INIT'),
        ('api-lock-repeated','hsl_api_lock_init()','fault-LOCK')):
        for suffix,marker in (('','FIRST_ERROR'),('-transient','FIRST_ERROR'),('-persistent','EXACT_STATE_TRACE')):
            add(name,'hsl_dev_init_core','rv = '+expression+';\n        SW_RTN_ON_ERROR(rv);',
                'SW_RTN_ON_ERROR('+expression+');',case+suffix,marker,active)
    for suffix,marker in (('','FIRST_ERROR'),('-transient','FIRST_ERROR'),('-persistent','EXACT_STATE_TRACE')):
        add('uk-clean-repeated','hsl_dev_cleanup_core','rv = sw_uk_cleanup();\n    SW_RTN_ON_ERROR(rv);',
            'SW_RTN_ON_ERROR(sw_uk_cleanup());','fault-UK_CLEAN'+suffix,marker,active)
    add('wrong-unspecified-dispatch','hsl_dev_dispatch_check','#if defined(ISIS) || defined(ISISC)',
        '#if defined(ISIS) || defined(ISISC) || defined(MHT)','dispatch-UNSPECIFIED','EXACT_STATE_TRACE',profile=='mht')
    add('vlan-residue-bypass','fal_vlan_init_available',
        'if (vlan_pool[dev_id] || vlan_db[dev_id] || vlan_list[dev_id])','if (0)',
        'vlan-residue1','FIRST_ERROR',active)
    for name,condition,case in (
        ('vlan-pool-bypass','vlan_db[dev_id] || vlan_list[dev_id]','vlan-residue1'),
        ('vlan-db-bypass','vlan_pool[dev_id] || vlan_list[dev_id]','vlan-residue2'),
        ('vlan-list-bypass','vlan_pool[dev_id] || vlan_db[dev_id]','vlan-residue4')):
        add(name,'fal_vlan_init_available','if (vlan_pool[dev_id] || vlan_db[dev_id] || vlan_list[dev_id])',
            'if ('+condition+')',case,'FIRST_ERROR',active)
    add('guard-not-consumed','hsl_dev_guard_end','*guard = NULL;','/* no consumption */',
        'token-hppe','GUARD_CONSUME',active)
    add('api-token-reused','hsl_dev_api_init_guarded','if (guard->phase != HSL_DEV_INIT_RESERVED)',
        'if (guard->phase != HSL_DEV_INIT_RESERVED && guard->phase != HSL_DEV_API_READY)',
        'token-hppe','FIRST_ERROR',active)
    add('own-flag-after-failed-child','hsl_dev_init_core','if (rv == SW_OK)\n                hsl_hppe_owned[dev_id] = A_TRUE;',
        'hsl_hppe_owned[dev_id] = A_TRUE;','nocpu','FIRST_ERROR',active)
    add('copied-guard-accepted','hsl_dev_guard_id','a_uint32_t dev_id;',
        'a_uint32_t dev_id; if (guard && guard->phase == HSL_DEV_INIT_RESERVED) return 0;',
        'token-hppe','FIRST_ERROR',active)
    add('running-end-init','hsl_dev_guard_end','case HSL_DEV_INIT_RESERVED:',
        'case HSL_DEV_INIT_RUNNING:\n    case HSL_DEV_INIT_RESERVED:','probe-SD','RUNNING_END_REJECT',active)
    add('running-end-clean','hsl_dev_guard_end','case HSL_DEV_CLEAN_RESERVED:',
        'case HSL_DEV_CLEAN_RUNNING:\n    case HSL_DEV_CLEAN_RESERVED:','probe-UK_CLEAN','RUNNING_END_REJECT',active)
    add('fal-first-error-lost','fal_init','return rv != SW_OK ? rv : end_rv;','return end_rv;',
        'fault-SD','FIRST_ERROR',active)
    add('fal-clean-first-error-lost','fal_cleanup','return rv != SW_OK ? rv : end_rv;','return end_rv;',
        'fault-UK_CLEAN','FIRST_ERROR',active)
    add('fal-error-guard-stuck','fal_init','end_rv = hsl_dev_guard_end(&guard);','end_rv = SW_OK;',
        'fault-SD-no-clean','EXACT_STATE_TRACE',active)
    add('legacy-new-hook-cleared','hsl_dev_cleanup_core','if (p_api->dev_clean == dev_clean)','if (1)',
        'legacy-hook-replacement','EXACT_STATE_TRACE',profile in ('nohppe','isis'))
    add('epoch-match-omitted','hppe_cleanup_owned','!owner || !hppe_cfg[dev_id] || hppe_owner_epoch[dev_id] != owner',
        '!owner || !hppe_cfg[dev_id]','epoch-recreate','FIRST_ERROR',active)
    add('epoch-reset-on-cleanup','hppe_cleanup','hppe_cfg[dev_id] = NULL;',
        'hppe_cfg[dev_id] = NULL; hppe_owner_epoch[dev_id] = 0;','fal-hppe','EXACT_STATE_TRACE',active)
    add('epoch-success-not-incremented','hppe_init','hppe_owner_epoch[dev_id]++;','/* no commit increment */',
        'fal-hppe','FIRST_ERROR',active)
    add('epoch-failed-constructor-increment','hppe_init','rv = hppe_dev_init(dev_id, cfg);',
        'rv = hppe_dev_init(dev_id, cfg); if (rv != SW_OK) { hppe_owner_epoch[dev_id]++; }',
        'epoch-retry-cpu','EXACT_STATE_TRACE',active)
    add('owned-output-pregranted','hppe_init_owned','rv = hppe_init(dev_id, cfg);',
        '*owner = hppe_owner_epoch[dev_id] + 1; rv = hppe_init(dev_id, cfg);','epoch-retry-cpu','FIRST_ERROR',active)
    add('owned-output-missing','hppe_init_owned','*owner = hppe_owner_epoch[dev_id];','/* no ownership output */',
        'fal-hppe','FIRST_ERROR',active)
    add('epoch-output-truncated','hppe_init_owned','*owner = hppe_owner_epoch[dev_id];','*owner = (a_uint32_t)hppe_owner_epoch[dev_id];',
        'epoch-max','FIRST_ERROR',active)
    add('epoch-cap-omitted','hppe_init','if (hppe_owner_epoch[dev_id] == (a_uint64_t)-1)','if (0)',
        'epoch-max','FIRST_ERROR',active)
    add('hsl-epoch-cleared-before-child','hsl_dev_cleanup_core','rv = hppe_cleanup_owned(dev_id, hsl_hppe_owner_epoch[dev_id]);',
        'hsl_hppe_owner_epoch[dev_id] = 0; rv = hppe_cleanup_owned(dev_id, hsl_hppe_owner_epoch[dev_id]);',
        'cleanup-mismatch','EXACT_STATE_TRACE',profile in ('hppe','kernel','user'))
    add('hsl-epoch-not-cleared','hsl_dev_cleanup_core','hsl_hppe_owner_epoch[dev_id] = 0;','/* retain stale ledger */',
        'fal-hppe','EXACT_STATE_TRACE',active)
    add('hsl-flag-cleared-before-child','hsl_dev_cleanup_core','rv = hppe_cleanup_owned(dev_id, hsl_hppe_owner_epoch[dev_id]);',
        'hsl_hppe_owned[dev_id] = A_FALSE; rv = hppe_cleanup_owned(dev_id, hsl_hppe_owner_epoch[dev_id]);',
        'cleanup-mismatch-retry','EXACT_STATE_TRACE',profile in ('hppe','kernel','user'))
    add('hsl-epoch-only-init-accepted','hsl_dev_init_available','hsl_hppe_owned[dev_id] || hsl_hppe_owner_epoch[dev_id]',
        'hsl_hppe_owned[dev_id]','ledger-epoch-only','FIRST_ERROR',active)
    add('hsl-flag-only-init-accepted','hsl_dev_init_available','hsl_hppe_owned[dev_id] || hsl_hppe_owner_epoch[dev_id]',
        'hsl_hppe_owner_epoch[dev_id]','ledger-flag-only','FIRST_ERROR',active)
    add('hsl-no-outer-clean-accepted','hsl_dev_cleanup_core','(!dev_ssdk_cfg[dev_id] || !hsl_hppe_owner_epoch[dev_id])',
        '(!hsl_hppe_owner_epoch[dev_id])','cleanup-no-outer','FIRST_ERROR',active)
    add('hsl-false-flag-epoch-clean-accepted','hsl_dev_cleanup_core','if (hsl_hppe_owner_epoch[dev_id])',
        'if (0)','ledger-epoch-only','FIRST_ERROR',active)
    add('changed-owner-availability-bypass','hsl_dev_init_begin','rv = hsl_dev_init_available(dev_id, cfg);',
        'rv = SW_OK;','held-outer-changed','CFG_COPY_OWNER',profile in ('nohppe','mht'))
    add('fal-id-priority','fal_init','HSL_DEV_ID_CHECK(dev_id);',
        'if (dev_id >= SW_MAX_NR_DEV) return SW_BAD_PARAM;','invalid3','FIRST_ERROR')
    add('cleanup-id-priority','hsl_dev_cleanup','HSL_DEV_ID_CHECK(dev_id);',
        'if (dev_id >= SW_MAX_NR_DEV) return SW_BAD_PARAM;','invalid3','FIRST_ERROR')
    add('null-admission-priority','hsl_dev_init_begin','if (!cfg || !guard)\n        return SW_BAD_PTR;',
        'if (!cfg || !guard)\n        return SW_BAD_PARAM;','fal-null','FIRST_ERROR')
    add('busy-silent-hook-write','hsl_dev_api_init_check','return hsl_dev_init_available(dev_id, NULL);',
        '#ifdef HPPE\n    if (dev_id < SW_MAX_NR_DEV && hsl_dev_guards[dev_id].phase != HSL_DEV_IDLE) { hsl_api_ptr_get(dev_id)->dev_clean = hppe_cleanup; }\n#endif\n    return hsl_dev_init_available(dev_id, NULL);',
        'probe-SD','REENTRY_STATE_UNCHANGED',profile in ('hppe','kernel','user'))
    add('busy-silent-nrphy-write','hsl_dev_init_available',
        'if (hsl_dev_guards[dev_id].phase != HSL_DEV_IDLE)\n        return SW_BUSY;',
        'if (hsl_dev_guards[dev_id].phase != HSL_DEV_IDLE) { dev_table[dev_id].nr_phy ^= 1; return SW_BUSY; }',
        'probe-SD','REENTRY_STATE_UNCHANGED',active)
    add('hsl-first-error-lost','hsl_dev_init','return rv != SW_OK ? rv : end_rv;','return end_rv;',
        'hsl-fault-SD','FIRST_ERROR',active)
    add('hsl-clean-first-error-lost','hsl_dev_cleanup','return rv != SW_OK ? rv : end_rv;','return end_rv;',
        'hsl-fault-UK_CLEAN','FIRST_ERROR',active)
    add('foreign-hook-clean-guard-omitted','hsl_dev_cleanup_core','if (p_api->dev_clean && p_api->dev_clean != hppe_cleanup)',
        'if (0)','cleanup-foreign-retry','FIRST_ERROR',active)
    add('failed-clean-silent-old-token-phy-write','hsl_port_prop_cleanup_owned',
        'if (!owner || p_port_info[dev_id] != owner)\n        return SW_BAD_STATE;',
        'if (!owner || p_port_info[dev_id] != owner) { if (owner) { owner->phy_id[15] ^= 1; } return SW_BAD_STATE; }',
        'cleanup-mismatch','EXACT_STATE_TRACE',profile in ('hppe','kernel','user'))
    add('owned-output-busy-priority','hppe_init_owned','return SW_BAD_STATE;','return SW_ALREADY_EXIST;',
        'epoch-api','FIRST_ERROR',active)
    add('owned-output-null-priority','hppe_init_owned','return SW_BAD_PTR;','return SW_BAD_PARAM;',
        'epoch-api','FIRST_ERROR',active)
    add('owned-clean-boundary-priority','hppe_cleanup_owned','return SW_BAD_STATE;','return SW_ALREADY_EXIST;',
        'epoch-api','FIRST_ERROR',active)
    add('owned-absent-C-check-omitted','hppe_cleanup_owned','!owner || !hppe_cfg[dev_id] || hppe_owner_epoch[dev_id] != owner',
        '!owner || hppe_owner_epoch[dev_id] != owner','epoch-retire-only','FIRST_ERROR',active)
    return rows
