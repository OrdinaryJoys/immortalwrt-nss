"""Clean-compiling directed semantic controls; every expected failure is exact."""


def once(text, before, after):
    if text.count(before) != 1:
        raise RuntimeError('mutation-occurrence:' + before)
    return text.replace(before, after, 1)


def variants(new, old, qca):
    rows = [
        ('prepare-owned-overwrite', 'qca_ssdk_phy_info_prepare', 'if (*prepared)', 'if (0)',
         'prepare-owned', 'PREPARE_RETURN'),
        ('prepare-wrong-type', 'qca_ssdk_phy_info_prepare', '= MAX_PHY_CHIP;', '= F1_PHY_CHIP;',
         'prepare-ok', 'META_COMPLETE_VALUE'),
        ('prepare-global-publication', 'qca_ssdk_phy_info_prepare', '*prepared = phy_information;',
         'phy_info[0] = phy_information;\n\t*prepared = phy_information;', 'prepare-ok', 'PREPARE_GLOBAL'),
        ('publish-outside-slot', 'qca_ssdk_phy_info_publish', 'i < SW_MAX_NR_DEV;', 'i < dev_num;',
         'publish-1-foreign-outside', 'PUBLISH_RETURN'),
        ('publish-missing', 'qca_ssdk_phy_info_publish', 'if (!prepared[i])', 'if (0)',
         'publish-2-missing', 'PUBLISH_RETURN'),
        ('publish-duplicate', 'qca_ssdk_phy_info_publish', 'if (prepared[i] == prepared[j])',
         'if (0 && prepared[i] == prepared[j])', 'publish-2-duplicate', 'PUBLISH_RETURN'),
        ('publish-no-consume', 'qca_ssdk_phy_info_publish', 'prepared[i] = NULL;', '(void)prepared[i];',
         'publish-2-ok', 'PUBLISH_CONSUME'),
        ('publish-before-validation', 'qca_ssdk_phy_info_publish',
         'for (i = 0; i < SW_MAX_NR_DEV; i++)',
         'port_bmp[0] ^= 1;\n\tfor (i = 0; i < SW_MAX_NR_DEV; i++)',
         'publish-1-foreign-outside', 'FINAL_GLOBAL'),
        ('legacy-busy-overwrite', 'qca_ssdk_phy_info_init', 'if (phy_info[dev_id])', 'if (0)',
         'legacy-1-busy', 'LEGACY_RETURN'),
        ('root-ignore-metadata-error', 'ssdk_alloc_priv', 'if (rv)\n\t\t\tgoto abort;',
         'if (0 && rv)\n\t\t\tgoto abort;', 'alloc-1-fault-3', 'ALLOC_RETURN'),
        ('root-metadata-leak', 'ssdk_alloc_priv', 'kfree(metadata[dev_id]);', '(void)metadata[dev_id];',
         'alloc-2-fault-4', 'FREE_ORDER'),
        ('root-vector-leak', 'ssdk_alloc_priv', 'kfree(prepared);', '(void)prepared;',
         'alloc-1-fault-2', 'OWNER_LEDGER'),
        ('root-global-cleanup', 'ssdk_alloc_priv', 'abort:\n', 'abort:\n\tssdk_netdev_cache_stop();\n',
         'alloc-1-fault-2', 'GLOBAL_CLEANUP'),
        ('root-drop-private-recheck', 'ssdk_alloc_priv',
         'if (qca_phy_priv_global) {\n\t\trv = -EBUSY;',
         'if (0 && qca_phy_priv_global) {\n\t\trv = -EBUSY;',
         'alloc-1-late-private', 'ALLOC_RETURN'),
        ('setup-fdb-flag', 'qca_fdb_sw_sync_work_setup', 'priv->fdb_work_initialized = true;',
         'priv->fdb_work_initialized = false;', 'alloc-1-ok', 'PRIVATE_COMPLETE_VALUE')]
    if qca:
        rows += [
            ('qca-address', 'qca_ssdk_qca808x_phy_info_prepare',
             'qca808x_phy_info[port_index].phy_address;',
             '(qca808x_phy_info[port_index].phy_address ^ 1u);', 'prepare-ok', 'META_COMPLETE_VALUE'),
            ('qca-bitmap', 'qca_ssdk_qca808x_phy_info_prepare', '*bitmap = port_bmp;', '*bitmap = port_bmp ^ 1u;',
             'prepare-ok', 'META_COMPLETE_VALUE')]
    else:
        rows.append(('prepare-bitmap-seed', 'qca_ssdk_phy_info_prepare', 'prepared_bitmap = *bitmap;',
                     'prepared_bitmap = 0;', 'prepare-ok', 'META_COMPLETE_VALUE'))
    for name, symbol, before, after, case, marker in rows:
        body = new['bodies'][symbol]
        yield {'name': name, 'symbol': symbol, 'before': body,
               'after': once(body, before, after), 'case': case, 'marker': marker,
               'classification': 'directed candidate source semantic mutant'}
    transfer = 'qca_phy_priv_global = prepared;'
    owner_rows = [
        ('private-swap', '{ struct qca_phy_priv *p = prepared[0]; prepared[0] = prepared[1]; prepared[1] = p; }',
         'ROOT_PRIVATE_SLOT'),
        ('private-alias', 'prepared[1] = prepared[0];', 'ROOT_PRIVATE_ALIAS'),
        ('private-missing', 'prepared[1] = NULL;', 'ROOT_PRIVATE_MISSING'),
        ('metadata-swap', '{ phy_info_t *p = phy_info[0]; phy_info[0] = phy_info[1]; phy_info[1] = p; }',
         'ROOT_METADATA_SLOT'),
        ('metadata-alias', 'phy_info[1] = phy_info[0];', 'ROOT_METADATA_ALIAS'),
        ('metadata-missing', 'phy_info[1] = NULL;', 'ROOT_METADATA_MISSING'),
        ('vector-offset', None, 'ROOT_VECTOR_OWNER')]
    body = new['bodies']['ssdk_alloc_priv']
    for flow in ('alloc', 'root'):
        for name, inject, marker in owner_rows:
            after = 'qca_phy_priv_global = prepared + 1;' if inject is None else inject + '\n\t' + transfer
            yield {'name': f'owner-{flow}-{name}', 'symbol': 'ssdk_alloc_priv', 'before': body,
                   'after': once(body, transfer, after), 'case': f'{flow}-2-ok', 'marker': marker,
                   'classification': 'directed candidate source semantic mutant',
                   'owner_guard_counterexample': (flow, name) in [('alloc', 'private-alias'), ('root', 'metadata-swap')]}
    for symbol, case, marker, name in [
        ('ssdk_alloc_priv', 'alloc-1-fault-3', 'STAGING_GLOBAL', 'old21-allocator-witness'),
        ('regi_init', 'root-1-fault-1', 'ROOT_GENERIC_OUT', 'old21-root-gate-witness')]:
        yield {'name': name, 'symbol': symbol, 'before': new['bodies'][symbol],
               'after': old['bodies'][symbol], 'case': case, 'marker': marker,
               'classification': 'complete old21 function body freshly compiled against selected current harness'}
