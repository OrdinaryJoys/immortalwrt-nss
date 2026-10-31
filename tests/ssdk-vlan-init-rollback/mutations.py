"""Bounded directed semantic source controls; no crash/compile credit."""


def once(text, before, after):
    if text.count(before) != 1:
        raise RuntimeError('mutation-not-unique:' + before)
    return text.replace(before, after, 1)


def variants(new, old, profile):
    result=[]
    b=new['bodies']

    def add(name,symbol,case,before,after,marker,classification='directed actual source-body mutant'):
        body=b[symbol]
        result.append(dict(name=name,symbol=symbol,case=case,before=body,after=once(body,before,after),
                           marker=marker,classification=classification))

    init='fal_vlan_init'
    add('missing-db-unwind',init,'dev0-nr257-fault3',
        'sid_pool_destroy(pool);\n        return SW_OUT_OF_MEM;',
        'return SW_OUT_OF_MEM;','NO_NEW_ORPHANS')
    add('missing-list-db-unwind',init,'dev0-nr257-fault4','aos_mem_free(db);','(void)db;','NO_NEW_ORPHANS')
    add('wrong-db-error',init,'dev0-nr257-fault3','return SW_OUT_OF_MEM;','return SW_FAIL;','VLAN_RETURN')
    add('wrong-list-error',init,'dev0-nr257-fault4',
        'aos_mem_free(db);\n        sid_pool_destroy(pool);\n        return SW_FAIL;',
        'aos_mem_free(db);\n        sid_pool_destroy(pool);\n        return SW_OUT_OF_MEM;','VLAN_RETURN')
    add('rollback-wrong-order',init,'dev0-nr257-fault4',
        'aos_mem_free(db);\n        sid_pool_destroy(pool);',
        'sid_pool_destroy(pool);\n        aos_mem_free(db);','EXACT_MODEL_TRACE')
    add('early-pool-publication',init,'dev0-nr257-fault3',
        'pool = sid_pool_creat(entry_nr, 0);','pool = sid_pool_creat(entry_nr, 0);\n    vlan_pool[dev_id] = pool;', 'EARLY_PUBLICATION')
    add('early-db-publication',init,'dev0-nr257',
        'db = aos_mem_alloc(entry_nr * (sizeof (v_array_t)));',
        'db = aos_mem_alloc(entry_nr * (sizeof (v_array_t)));\n    vlan_db[dev_id] = db;', 'EARLY_PUBLICATION')
    guard='if (vlan_pool[dev_id] || vlan_db[dev_id] || vlan_list[dev_id])'
    add('borrow-guard-and',init,'dev0-borrow1-nr257',guard,
        'if (vlan_pool[dev_id] && vlan_db[dev_id] && vlan_list[dev_id])','BORROWED_ALLOCATION')
    add('borrow-guard-pool-only',init,'dev0-borrow2-nr257',guard,
        'if (vlan_pool[dev_id])','BORROWED_ALLOCATION')
    add('guard-before-hw-bypass',init,'dev0-hw-borrow7',
        'if (A_TRUE == p_dev->hw_vlan_query)',
        'if (vlan_pool[dev_id] || vlan_db[dev_id] || vlan_list[dev_id]) return SW_ALREADY_EXIST;\n    if (A_TRUE == p_dev->hw_vlan_query)', 'VLAN_RETURN')
    add('count-before-hw-bypass',init,'dev0-hw-nr0',
        'if (A_TRUE == p_dev->hw_vlan_query)',
        'if (!p_dev->nr_vlans) return SW_FAIL;\n    if (A_TRUE == p_dev->hw_vlan_query)', 'VLAN_RETURN')
    add('reject-capacity4096',init,'dev0-nr4096','4096 < entry_nr','4096 <= entry_nr','VLAN_RETURN')
    add('accept-capacity4097',init,'dev0-nr4097','4096 < entry_nr','65535 < entry_nr','VLAN_RETURN')
    add('wrong-dev-publication',init,'dev0-nr257','vlan_pool[dev_id] = pool;',
        'vlan_pool[(dev_id + 1) % SW_MAX_NR_DEV] = pool;','POINTER_IDENTITY_BEFORE_DEREF')
    add('wrong-db-publication',init,'dev0-nr257','vlan_db[dev_id] = db;',
        'vlan_db[dev_id] = vlan_db[(dev_id + 1) % SW_MAX_NR_DEV];','OWNED_IDENTITY_SHAPE')
    add('global-cleanup-not-local-unwind',init,'dev0-nr257-fault3',
        'sid_pool_destroy(pool);\n        return SW_OUT_OF_MEM;',
        'fal_vlan_cleanup(dev_id);\n        return SW_OUT_OF_MEM;','NO_NEW_ORPHANS')
    add('missing-explicit-db-zero',init,'dev0-nr257','aos_mem_zero(db, entry_nr * (sizeof (v_array_t)));',
        '(void)db;', 'DB_COMPLETE_ZERO' if profile=='generic-poison-stress' else 'EXACT_MODEL_TRACE',
        'unchanged explicit-zero call contract control; poison failure is NON-Linux strengthening, not stock zero-allocation fault')

    pool='sid_pool_creat'
    add('pool-inner-fail-no-header-free',pool,'dev0-nr257-fault2','aos_mem_free(pool);','(void)pool;','NO_NEW_ORPHANS')
    add('pool-wrong-min',pool,'pool-nr257-fault0','pool->id_min     = min_id;',
        'pool->id_min     = min_id + 1;','POOL_COMPLETE_FIELDS')
    add('pool-width256',pool,'dev0-nr256','ID_NR_IN_U8 >= id_nr','ID_NR_IN_U8 > id_nr','ALLOC_EXACT_SIZE')
    body=b[pool];before='p_id[i] = i;'
    if body.count(before)!=3:raise RuntimeError('exact-three-pool-id-branches')
    result.append(dict(name='pool-id-sequence',symbol=pool,case='dev0-nr257',before=body,
        after=body.replace(before,'p_id[i] = i + 1;'),marker='POOL_ID_CONTENTS',classification='directed actual source-body mutant (all three explicit width branches)'))
    list_='sll_creat'
    add('list-wrong-flags',list_,'dev0-nr257','head->flag    = flag;','head->flag    = flag ^ LL_IN_ORDER;','LIST_FIELDS_CALLBACKS')
    add('list-null-callback',list_,'dev0-nr257','head->nd_cmp  = cmp_func;',
        'head->nd_cmp  = cmp_func == NULL ? cmp_func : NULL;','LIST_FIELDS_CALLBACKS')
    add('list-node-identity',list_,'dev0-nr257','head->free_nd = &(node[i]);','head->free_nd = &(node[0]);', 'LIST_NODE_IDENTITY_BEFORE_READ')
    add('comparison-order','_fal_vlan_entry_cmp','dev0-nr257','return LL_CMP_GREATER;','return LL_CMP_SMALLER;','CMP_ORDER')
    add('getter-valid-null','hsl_dev_ptr_get','dev0-missing','return &dev_table[dev_id];','return NULL;','VLAN_RETURN')
    add('getter-unrelated-metadata-write','hsl_dev_ptr_get','dev0-missing','return &dev_table[dev_id];',
        'dev_table[dev_id].dev_id ^= 1;\n    return &dev_table[dev_id];','HSL_METADATA_UNCHANGED')
    cleanup='fal_vlan_cleanup'
    add('cleanup-db-not-cleared',cleanup,'dev0-repeat','vlan_db[dev_id] = NULL;','(void)dev_id;','FREE_ONCE')
    add('cleanup-list-orphan',cleanup,'dev0-repeat','sll_destroy(vlan_list[dev_id]);','(void)vlan_list[dev_id];','NO_NEW_ORPHANS')
    return result
