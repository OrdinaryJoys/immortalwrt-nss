"""Directed clean native negatives; never credit compiler/sanitizer failures."""


def once(text,before,after):
    if text.count(before)!=1:raise RuntimeError('mutation-occurrence:'+before)
    return text.replace(before,after,1)


def variants(new,old,profile):
    rows=[]
    symbol='ssdk_switch_device_num_init';anchor='ssdk_dt_global.ssdk_dt_switch_nodes = nodes;'
    rows += [
        ('vector-offset',symbol,anchor,'nodes++;\n\t'+anchor,'disabled-2','VECTOR_IDENTITY_SHAPE'),
        ('slot-swap',symbol,anchor,'{ ssdk_dt_cfg *swap = nodes[0]; nodes[0] = nodes[1]; nodes[1] = swap; }\n\t'+anchor,'disabled-2','SLOT_IDENTITY_SHAPE'),
        ('slot-alias',symbol,anchor,'nodes[1] = nodes[0];\n\t'+anchor,'disabled-2','SLOT_IDENTITY_SHAPE'),
        ('slot-missing',symbol,anchor,'nodes[1] = NULL;\n\t'+anchor,'disabled-2','SLOT_IDENTITY_SHAPE')]
    if profile=='noof':
        # non-OF always defaults to one real modeled slot; offset remains safe.
        rows=[(name,symbol,before,after,'noof-default-2',marker)
              for name,symbol,before,after,_case,marker in rows[:1]]
    if profile=='modern':
        rows += [
            ('id-extra-cell','ssdk_dt_read_device_id','len != sizeof(value)','len != sizeof(value) && len != 2 * sizeof(value)','direct-id-length-8','ID_RETURN_VALUE'),
            ('id-fixed-bound','ssdk_dt_read_device_id','value >= dev_num || value >= SW_MAX_NR_DEV','value >= dev_num','direct-id-fixed-only','ID_RETURN_VALUE'),
            ('lookup-disabled-leak','ssdk_dt_get_switch_node','of_node_put(*switch_node);','(void)*switch_node;','lookup-disabled','NODE_REF_LEDGER'),
            ('lookup-disabled-escape','ssdk_dt_get_switch_node','of_node_put(*switch_node);\n\t\t*switch_node = NULL;','of_node_put(*switch_node);','lookup-disabled','LOOKUP_OWNER_ESCAPE'),
            ('lookup-double-from-put','ssdk_dt_get_switch_node','*switch_node = of_find_node_by_name(switch_instance, ess_switch_name);','*switch_node = of_find_node_by_name(switch_instance, ess_switch_name);\n\tof_node_put(switch_instance);','lookup-ok','OF_DOUBLE_PUT'),
            ('duplicate-id','ssdk_dt_prepare_nodes','if (seen[prepared[num].id])','if (0 && seen[prepared[num].id])','duplicate','PREFLIGHT_BEFORE_ALLOC'),
            ('allocation-before-preflight',symbol,'ret = ssdk_dt_prepare_nodes(prepared, dev_num);','ret = 0;','topology-1-ok','ALL_NODES_BEFORE_ALLOC'),
            ('prepare-ref-leak',symbol,'of_node_put(prepared[num].node);','(void)prepared[num].node;','later-mode-error','NODE_REF_LEDGER'),
            ('adopt-ordinal-not-id',symbol,'cfg = nodes[dev_id];','cfg = nodes[num];','permutation-2','CFG_FULL_VALUE'),
            ('map-ordinal-not-id',symbol,'ssdk_dt_admitted[num].id = dev_id;','ssdk_dt_admitted[num].id = num;','permutation-2','ADMITTED_MAP'),
            ('exit-node-leak','ssdk_switch_device_num_exit','of_node_put(ssdk_dt_global.ssdk_dt_switch_nodes[dev_id]->of_node);','(void)ssdk_dt_global.ssdk_dt_switch_nodes[dev_id]->of_node;','parse-1','NODE_REF_LEDGER'),
            ('exit-map-stale','ssdk_switch_device_num_exit','memset(ssdk_dt_admitted, 0, sizeof(ssdk_dt_admitted));','(void)ssdk_dt_admitted;','parse-1','MAP_RETIRED'),
            ('parser-reference-claim','ssdk_dt_parse','switch_node = ssdk_dt_priv->of_node;','switch_node = ssdk_dt_priv->of_node;\n\t(void)of_node_get(switch_node);','parse-1','LEAF_ID_NODE_OWNER'),
            ('parser-drop-emulation','ssdk_dt_parse','ssdk_dt_priv->is_emulation = A_TRUE;','(void)ssdk_dt_priv;','parse-emulation','PARSE_COMPLETE_WRITEBACK'),
            ('parser-drop-tm-tick','ssdk_dt_parse','ssdk_dt_priv->tm_tick_mode = mode;','(void)mode;','parse-1','PARSE_COMPLETE_WRITEBACK'),
            ('parser-drop-bm-tick','ssdk_dt_parse','ssdk_dt_priv->bm_tick_mode = mode;','(void)mode;','parse-1','PARSE_COMPLETE_WRITEBACK'),
            ('parser-drop-clock-store','ssdk_dt_parse',
             'ssdk_dt_priv->cmnblk_clk = of_clk_get_by_name(switch_node, "cmn_ahb_clk");\n\t\tif (!of_property_read_u32(switch_node, "tm_tick_mode"',
             '(void)of_clk_get_by_name(switch_node, "cmn_ahb_clk");\n\t\tif (!of_property_read_u32(switch_node, "tm_tick_mode"',
             'parse-1','PARSE_COMPLETE_WRITEBACK'),
            ('root-private-after-admission-error','regi_init','if (rv)\n\t\treturn rv;','if (rv) { ssdk_alloc_priv(dev_num); return rv; }','root-1-fault-1','ROOT_PRIVATE_COUNT')]
    for name,symbol,before,after,case,marker in rows:
        body=new['bodies'][symbol]
        yield dict(name=name,symbol=symbol,before=body,after=once(body,before,after),case=case,marker=marker,
                   classification='directed source semantic mutant with pre-payload safe owner gates')
    if profile=='modern':
        symbol='ssdk_switch_device_num_init'
        yield dict(name='old22-topology-no-preflight',symbol=symbol,before=new['bodies'][symbol],after=old['bodies'][symbol],
                   case='id-dynamic',marker='PREFLIGHT_BEFORE_ALLOC',classification='complete old22 topology body freshly compiled; safe admission boundary witness')
