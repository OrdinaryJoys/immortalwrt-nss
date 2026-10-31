"""Directed complete-body controls. Compiler/crash/sanitizer failures earn no credit."""
import re


def once(text,before,after):
    if text.count(before)!=1:raise RuntimeError('mutation-not-unique:'+before)
    return text.replace(before,after,1)


def variants(new,old,profile):
    rename={'hppe_dev_init':'real_dev','hppe_portproperty_init':'real_prop','hsl_port_prop_set':'real_set',
            'hsl_port_prop_init':'real_reset'}
    b={n:re.sub(r'\b'+n+r'\b',rename[n],raw,count=1) if n in rename else raw for n,raw in new['bodies'].items()}
    result=[]
    pattern=r'rv = ([^;\n]+);\n([ \t]*)SW_RTN_ON_ERROR\(rv\);'
    expected={'hppe_init':['DEV','RESET','PALLOC','PROP'],
              'hppe_portproperty_init':['SET0','SET3','SET1','SET2','SET4'],'hppe_cleanup':['CLEAN']}
    for symbol,sites in expected.items():
        body=b[symbol];matches=list(re.finditer(pattern,body))
        if len(matches)!=len(sites):raise RuntimeError('exact-ten-sites:'+symbol)
        for m,site in zip(matches,sites):
            if profile=='both' and site in ('RESET','PALLOC','PROP'):continue
            call,indent=m.groups();after='rv = SW_OK; (void)rv;\n'+indent+'SW_RTN_ON_ERROR('+call+');'
            # Equal setter spellings occur in distinct switch branches; bind the exact matched site.
            mutated=body[:m.start()]+after+body[m.end():]
            result.append(dict(name='double-evaluate-'+site,symbol=symbol,before=body,after=mutated,
                probes=[('synthetic-'+site+'-'+mode,'SINGLE_EVALUATION' if mode=='persistent' else 'FIRST_RETURN')
                        for mode in ('transient','different','persistent')],
                classification='single038 call site restored to repeated evaluation; synthetic helper failures explicitly artificial'))
    def add(name,symbol,case,before,after,marker,classification='directed actual source state/callback mutant'):
        body=b[symbol];result.append(dict(name=name,symbol=symbol,before=body,after=once(body,before,after),
                                         probes=[(case,marker)],classification=classification))
    add('dev-union-to-xor','hppe_dev_init','dev0-cpu-zero','cfg->port_cfg.lan_bmp | cfg->port_cfg.wan_bmp',
        'cfg->port_cfg.lan_bmp ^ cfg->port_cfg.wan_bmp','EXACT_MODEL_TRACE')
    add('dev-no-lowest-cpu-break','hppe_dev_init','dev0-cpu-lowest','break;','(void)port_nr;','FIRST_RETURN')
    add('setter-wrong-row','hsl_port_prop_set','helpers-retain-state','p_port_info[dev_id]->property[p_type]',
        'p_port_info[dev_id]->property[(p_type + 1) % HSL_PP_BUTT]','EXACT_MODEL_TRACE')
    if profile!='both':
        add('api-wrong-sd-token','hppe_init','dev0-callback','p_api->reg_get = sd_reg_hdr_get;',
            'p_api->reg_get = sd_reg_hdr_set;','API_FIELD_IDENTITY')
    add('unapproved-dev-failure-free','hppe_init','dev0-cpu-none',
        'rv = hppe_dev_init(dev_id, cfg);',
        'rv = hppe_dev_init(dev_id, cfg);\n    if (rv != SW_OK) { aos_mem_free(hppe_cfg[dev_id]); hppe_cfg[dev_id] = NULL; }',
        'EXACT_MODEL_TRACE','owner-boundary preservation control;038 deliberately adds NO rollback, not an endorsement of owner gap')
    add('cleanup-frees-cfg-on-dependency-error','hppe_cleanup','synthetic-CLEAN-transient',
        'rv = hsl_port_prop_cleanup_by_dev(dev_id);',
        'rv = hsl_port_prop_cleanup_by_dev(dev_id);\n        if (rv != SW_OK) { aos_mem_free(hppe_cfg[dev_id]); hppe_cfg[dev_id] = NULL; }',
        'EXACT_MODEL_TRACE','dependency first-error/owner preservation control, not lifecycle closure')
    if profile!='both':
        add('reset-silently-frees-old-port','hsl_port_prop_init','dev0-repeat','p_port_info[dev_id] = NULL;',
            'if (p_port_info[dev_id]) aos_mem_free(p_port_info[dev_id]);\n    p_port_info[dev_id] = NULL;',
            'EXACT_MODEL_TRACE','preserve unchanged reset-loss OPEN boundary; not a proposed owner repair')
    return result
