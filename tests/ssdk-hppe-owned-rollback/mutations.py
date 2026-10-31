"""Directed complete-body source mutations; obligations live independently in runner."""
def once(text, before, after):
    if text.count(before) != 1 or before == after:
        raise RuntimeError('mutation-unique-changing-target')
    return text.replace(before, after, 1)


def variants(new, profile):
    b=new['bodies'];rows=[]
    def add(name,symbol,old,replacement,case,marker,active=True):
        if not active:return
        after=once(b[symbol],old,replacement)
        rename={'hsl_port_prop_build_portmap_set':'real_map','hsl_port_prop_build_set':'real_set',
                'hsl_port_prop_build_publish':'real_publish','hsl_port_prop_cleanup_owned':'real_owned'}
        before=b[symbol]
        if symbol in rename:
            before=before.replace(symbol,rename[symbol],1);after=after.replace(symbol,rename[symbol],1)
        rows.append(dict(name=name,symbol=symbol,before=before,after=after,case=case,marker=marker,classification='directed actual source mutant'))
    active=profile!='both'
    add('nullcfg-error','hppe_init','return SW_BAD_PTR;','return SW_BAD_PARAM;','d0-nullcfg','FIRST_ERROR')
    add('cfg-admission','hppe_init','hppe_cfg[dev_id] || hppe_port_owner[dev_id]','hppe_port_owner[dev_id]','d0-borrow1','PRIVATE_BEFORE_PUBLICATION',active)
    add('token-admission','hppe_init','hppe_cfg[dev_id] || hppe_port_owner[dev_id]','hppe_cfg[dev_id]','d0-tokenold','PRIVATE_BEFORE_PUBLICATION',active)
    add('foreign-hook','hppe_init','p_api->dev_clean && p_api->dev_clean != hppe_cleanup','0','d0-foreignhook','FIRST_ERROR',active)
    add('restore-metadata','hppe_init','*pdev = saved_dev;','(void)saved_dev;','d0-nocpu','EXACT_OWNER_TRACE')
    add('abort-cfg-leak','hppe_init','aos_mem_free(new_cfg);','(void)new_cfg;','d0-nocpu','EXACT_OWNER_TRACE')
    add('abort-private-leak','hppe_init','hsl_port_prop_build_abort(&owner);','(void)owner;','d0-synthetic-set','EXACT_OWNER_TRACE',active)
    add('reverse-free-order','hppe_init','hsl_port_prop_build_abort(&owner);','aos_mem_free(new_cfg); new_cfg = NULL; hsl_port_prop_build_abort(&owner);','d0-synthetic-set','EXACT_OWNER_TRACE',active)
    add('abort-first-error','hppe_init','out:\n    hppe_initializing[dev_id] = A_FALSE;\n    return rv;','out:\n    hppe_initializing[dev_id] = A_FALSE;\n    return SW_OK;','d0-nocpu','FIRST_ERROR')
    add('busy-success','hppe_init','hppe_initializing[dev_id] = A_FALSE;\n    return SW_OK;','hppe_initializing[dev_id] = A_TRUE;\n    return SW_OK;','d0-repeat','FIRST_ERROR')
    add('busy-failure','hppe_init','out:\n    hppe_initializing[dev_id] = A_FALSE;','out:\n    hppe_initializing[dev_id] = A_TRUE;','d0-cfg-first','FIRST_ERROR')
    add('nested-init-domain','hppe_init','return SW_BUSY;','return SW_ALREADY_EXIST;','d0-nested','NESTED_BUSY_DOMAIN')
    add('nested-clean-domain','hppe_cleanup','return SW_BUSY;','return SW_ALREADY_EXIST;','d0-nested','NESTED_BUSY_DOMAIN')
    add('no-token-store','hppe_init','hppe_port_owner[dev_id] = published_owner;','(void)published_owner;','d0-direct','EXACT_OWNER_TRACE',active)
    add('api-wrong-token','hppe_init','p_api->reg_get = sd_reg_hdr_get;','p_api->reg_get = sd_reg_hdr_set;','d0-direct','API_IDENTITY',active)
    add('cleanup-mismatch-error','hsl_port_prop_cleanup_owned','return SW_BAD_STATE;','return SW_ALREADY_EXIST;','d0-mismatch','FIRST_ERROR',active)
    add('combined-unowned-clean','hppe_cleanup','if (hppe_port_owner[dev_id]) {','if (p_port_info[dev_id]) {','d0-borrow2','FIRST_ERROR',not active)
    add('publish-consume','hsl_port_prop_build_publish','*owner = NULL;','/* handle deliberately not consumed */','d0-builders','PUBLISH_CONSUME')
    add('publish-conflict-code','hsl_port_prop_build_publish','SW_RTN_ON_ERROR(rv);','if (rv != SW_OK) return SW_BAD_STATE;','d0-builders','FIRST_ERROR')
    add('abort-consume','hsl_port_prop_build_abort','*owner = NULL;','/* handle deliberately not consumed */','d0-builders','ABORT_CONSUME')
    add('map-upper-bound','hsl_port_prop_build_portmap_set','port_id >= SW_MAX_NR_PORT','port_id > SW_MAX_NR_PORT','d0-builders','FIRST_ERROR')
    add('setter-negative-enum-error','hsl_port_prop_build_set','return SW_BAD_PARAM;','return SW_BAD_VALUE;','d0-builders','FIRST_ERROR')
    add('setter-row','hsl_port_prop_build_set','owner->property[p_type]','owner->property[(p_type + 1) % HSL_PP_BUTT]','d0-cpu0','EXACT_OWNER_TRACE',active)
    add('alloc-occupied-out-error','hsl_port_prop_build_alloc','return SW_BAD_STATE;','return SW_ALREADY_EXIST;','d0-builders','FIRST_ERROR')
    add('existing-cfg-code','hppe_init','if (hppe_cfg[dev_id] || hppe_port_owner[dev_id])\n        return SW_ALREADY_EXIST;',
        'if (hppe_cfg[dev_id] || hppe_port_owner[dev_id])\n        return SW_BAD_STATE;','d0-borrow1','FIRST_ERROR')
    add('private-cfg-early-publish','hppe_init','rv = hppe_dev_init(dev_id, cfg);',
        'hppe_cfg[dev_id] = new_cfg; rv = hppe_dev_init(dev_id, cfg);','d0-cpu0','PRIVATE_BEFORE_PUBLICATION',active)
    add('abort-frees-foreign','hppe_init','hsl_port_prop_build_abort(&owner);',
        'if (p_port_info[dev_id]) { aos_mem_free(p_port_info[dev_id]); }\n    hsl_port_prop_build_abort(&owner);','d0-conflict','ONLY_OWNED_FREE',active)
    add('cleanup-ignores-identity','hsl_port_prop_cleanup_owned','!owner || p_port_info[dev_id] != owner',
        '!owner','d0-mismatch','ONLY_OWNED_FREE',active)
    add('cleanup-token-not-cleared','hppe_cleanup','hppe_port_owner[dev_id] = NULL;',
        '/* stale token */','d0-direct','OWNER_BEFORE_DEREF',active)
    add('cross-device-busy','hppe_init','if (hppe_initializing[dev_id])',
        'if (hppe_initializing[0] || hppe_initializing[1] || hppe_initializing[2])','d0-nested','NESTED_BUSY_DOMAIN')
    # Valid data condition from Q01, not test-name/flow/trace-aware corruption.
    add('builder-valid-wrong-row','hsl_port_prop_build_set','owner->property[p_type]',
        'owner->property[(owner->dev_portmap == (1u << 15) && p_type == HSL_PP_PHY) ? HSL_PP_CPU : p_type]',
        'd0-builders','BUILDER_PRIVATE_PAYLOAD')
    add('builder-delete-map-store','hsl_port_prop_build_portmap_set','SW_PBMP_ADD_PORT(owner->dev_portmap, port_id);',
        '/* valid map store deleted */','d0-builders','BUILDER_PRIVATE_PAYLOAD')
    add('builder-delete-set-store','hsl_port_prop_build_set','SW_PBMP_ADD_PORT(owner->property[p_type], port_id);',
        '/* valid property store deleted */','d0-builders','BUILDER_PRIVATE_PAYLOAD')
    add('builder-private-phy-corrupt','hsl_port_prop_build_set','SW_PBMP_ADD_PORT(owner->property[p_type], port_id);',
        'SW_PBMP_ADD_PORT(owner->property[p_type], port_id); owner->phy_id[port_id] = 1;',
        'd0-builders','BUILDER_PRIVATE_PAYLOAD')
    for field,suffix in (('dev_portmap','map'),('property[HSL_PP_CPU]','row'),('phy_id[15]','phy')):
        add('builder-post-'+suffix+'-corrupt','hsl_port_prop_build_publish','p_port_info[dev_id] = *owner;',
            'p_port_info[dev_id] = *owner; p_port_info[dev_id]->'+field+' ^= (1u << 7);',
            'd0-builders','BUILDER_PUBLISHED_PAYLOAD')
    return rows
