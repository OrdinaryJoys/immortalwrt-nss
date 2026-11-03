"""Independent command inputs and mathematical action/payload expectations."""
import errno
import ipaddress

FIELDS = {'rule_type': 1, 'ipv6_prefix': '2001:db8::', 'ipv6_prefix_len': 32,
          'ipv6_suffix': '2001:db8:1::', 'ipv6_suffix_len': 64,
          'ipv4_prefix': '192.0.2.0', 'ipv4_prefix_len': 24, 'ea_len': 8, 'psid_offset': 6}


def mapping(**overrides):
    values = dict(FIELDS, **overrides)
    return ' '.join(str(k)+'='+str(v) for k, v in values.items())


def payload(values):
    if values == 'bmr-delete':
        values = dict.fromkeys(FIELDS, 0)
        values.update(rule_type=1, ipv6_prefix='::', ipv6_suffix='::', ipv4_prefix='0.0.0.0')
    def v6(key):
        number = int(ipaddress.IPv6Address(values[key]))
        return ','.join(format((number >> shift) & 0xffffffff, '08x') for shift in (96,64,32,0))
    return (' rule='+str(values['rule_type'])+' p6='+v6('ipv6_prefix')+' l6='+str(values['ipv6_prefix_len'])+
            ' s6='+v6('ipv6_suffix')+' sl6='+str(values['ipv6_suffix_len'])+
            ' p4='+format(int(ipaddress.IPv4Address(values['ipv4_prefix'])), '08x')+
            ' l4='+str(values['ipv4_prefix_len'])+' ea='+str(values['ea_len'])+' psid='+str(values['psid_offset']))


def case(name, command, mode, result=0, gets=(), selected=None, op=None, values=None,
         status=0, parse_failed=False, selector=0, initial_frag=0, final_frag=None,
         oom=0, repeat=1, preflight=False):
    return dict(name=name, command=command.encode(), mode=mode, result=result, gets=tuple(gets),
                selected=selected, op=op, values=values, status=status, parse_failed=parse_failed,
                selector=selector, initial_frag=initial_frag,
                final_frag=initial_frag if final_frag is None else final_frag,
                oom=oom, repeat=repeat, preflight=preflight)


CASES = [
    case('add-bmr', 'netdev=ath0 '+mapping()+'\n', 0, gets=('ath0',), selected=0, op='add', values=FIELDS),
    case('add-fmr', 'netdev=ath1 '+mapping(rule_type=2), 0, gets=('ath1',), selected=1, op='add', values=dict(FIELDS, rule_type=2)),
    case('delete-bmr', 'netdev=ath0 rule_type=1', 1, gets=('ath0',), selected=0, op='del', values='bmr-delete'),
    case('delete-fmr', 'netdev=ath1 '+mapping(rule_type=2), 1, gets=('ath1',), selected=1, op='del', values=dict(FIELDS, rule_type=2)),
    case('flush', 'netdev=ath0', 2, gets=('ath0',), selected=0, op='flush'),
    case('frag-one', 'frag_id_update=1', 3, final_frag=1),
    case('frag-zero', 'frag_id_update=0\n', 3, initial_frag=1, final_frag=0),
    case('frag-missing', ' ', 3, -errno.EINVAL, initial_frag=1),
    case('frag-unknown-only', 'unknown=1', 3, -errno.EINVAL, initial_frag=1),
    case('frag-forbidden-netdev', 'netdev=ath0 frag_id_update=1', 3, -errno.EINVAL,
         gets=('ath0',), selected=0, initial_frag=1),
    case('frag-repeat-valid', 'frag_id_update=1 frag_id_update=0', 3, initial_frag=1, final_frag=0),
    case('duplicate-different', 'netdev=ath0 netdev=ath1', 2, gets=('ath0','ath1'), selected=1, op='flush'),
    case('duplicate-same', 'netdev=ath0 netdev=ath0', 2, gets=('ath0','ath0'), selected=0, op='flush'),
    case('duplicate-three', 'netdev=ath1 netdev=ath0 netdev=ath1', 2,
         gets=('ath1','ath0','ath1'), selected=1, op='flush'),
    case('duplicate-last-missing', 'netdev=ath0 netdev=missing', 2, -errno.ENODEV,
         gets=('ath0','missing'), selected=0, parse_failed=True),
    case('first-missing', 'netdev=missing netdev=ath1', 2, -errno.ENODEV,
         gets=('missing',), parse_failed=True),
    case('empty-netdev', 'netdev=', 2, -errno.ENODEV, gets=('',), parse_failed=True),
    case('duplicate-empty-netdev', 'netdev=ath0 netdev=', 2, -errno.ENODEV,
         gets=('ath0',''), selected=0, parse_failed=True),
    case('missing-value-after-netdev', 'netdev=ath0 token', 2, -errno.EINVAL,
         gets=('ath0',), selected=0, parse_failed=True),
    case('zero-rule', 'netdev=ath0 rule_type=0', 1, -errno.EINVAL,
         gets=('ath0',), selected=0, parse_failed=True),
    case('duplicate-parse-error', 'netdev=ath0 netdev=ath1 rule_type=bad', 0, -errno.EINVAL,
         gets=('ath0','ath1'), selected=1, parse_failed=True),
    case('missing-netdev', mapping(), 0, -errno.EINVAL),
    case('missing-rule', 'netdev=ath0', 1, -errno.EINVAL, gets=('ath0',), selected=0),
    case('missing-map-fields', 'netdev=ath0 rule_type=1', 0, -errno.EINVAL, gets=('ath0',), selected=0),
    case('empty-request', '', 3, -errno.E2BIG, initial_frag=1, preflight=True),
    case('whitespace-map', '  \n', 0, -errno.EINVAL),
    case('null-buffer', 'netdev=ath0', 2, -errno.EINVAL, selector=1, preflight=True),
    case('null-lenp', 'netdev=ath0', 2, -errno.EINVAL, selector=2, preflight=True),
    case('read', 'netdev=ath0', 2, -errno.EINVAL, selector=3, preflight=True),
    case('size-max', 'netdev=ath0', 2, -errno.E2BIG, selector=4, preflight=True),
    case('oversized', 'x'*1025, 0, -errno.E2BIG, preflight=True),
    case('full-buffer', 'frag_id_update=0'+' '*(1024-len('frag_id_update=0')), 3, initial_frag=1, final_frag=0),
    case('oom', 'netdev=ath0', 2, -errno.ENOMEM, oom=1),
    case('oom-retry', 'netdev=ath0', 2, -errno.ENOMEM, gets=('ath0',), selected=0, op='flush', oom=1, repeat=2),
    case('invalid-mode', 'netdev=ath0', 99, -errno.EINVAL, gets=('ath0',), selected=0),
    case('invalid-frag-value', 'frag_id_update=2', 3, -errno.EINVAL, initial_frag=1, parse_failed=True),
]
for field in ('rule_type','ipv4_prefix_len','ipv6_prefix_len','ipv6_suffix_len','ea_len','psid_offset'):
    CASES.append(case('empty-'+field, 'netdev=ath0 '+field+'=', 0, -errno.EINVAL,
                      gets=('ath0',), selected=0, parse_failed=True))
CASES.append(case('empty-frag', 'frag_id_update=', 3, -errno.EINVAL, initial_frag=1, parse_failed=True))
zero_values = dict(FIELDS, ipv4_prefix_len=0, ipv6_prefix_len=0, ipv6_suffix_len=0, ea_len=0, psid_offset=0)
CASES.append(case('zero-fields', 'netdev=ath0 '+mapping(**zero_values), 0,
                  gets=('ath0',), selected=0, op='add', values=zero_values))
for op, mode, command, values, failure in (
    ('add',0,'netdev=ath0 '+mapping(),FIELDS,5),
    ('del',1,'netdev=ath0 rule_type=1','bmr-delete',6),
    ('flush',2,'netdev=ath0',None,7)):
    # Exact enum ordinals from the pinned public enum; actual C enum is extracted.
    for label, status, result in (('invalid-param',9,-errno.EINVAL),('invalid-rule',10,-errno.EINVAL),
                                  ('no-node',8,-errno.ENODEV),('tx-failure',failure,-errno.EIO)):
        CASES.append(case('lower-'+op+'-'+label, command, mode, result, gets=('ath0',), selected=0,
                          op=op, values=values, status=status))
CASES.append(case('lower-unknown', 'netdev=ath0', 2, -errno.EIO, gets=('ath0',), selected=0, op='flush', status=123))
CASES.append(case('lower-retry', 'netdev=ath0', 2, -errno.EIO, gets=('ath0',), selected=0,
                  op='flush', status=7, repeat=2))
CASES = tuple(CASES)


def expected_trace(c):
    lines=[]; attempts=0; releases=0; calls=0
    for step in range(c['repeat']):
        failed_alloc=c['oom'] and not step
        status=0 if step else c['status']
        result=0 if step else c['result']
        selected=None
        if not c['preflight']:
            attempts+=1; lines.append('ALLOC 1025 '+('FAIL' if failed_alloc else 'OK'))
            if not failed_alloc:
                for name in c['gets']:
                    index={'ath0':0,'ath1':1,'foreign':2}.get(name)
                    lines.append('GET '+name+' '+('NONE' if index is None else str(index)))
                    if index is None:
                        break
                    if selected is not None:
                        lines.append('PUT '+str(selected))
                    selected=index
                if c['parse_failed']:
                    if selected is not None:
                        lines.append('PUT '+str(selected)); selected=None
                    lines.append('FREE'); releases+=1
                else:
                    lines.append('FREE'); releases+=1
                    if c['op']:
                        calls+=1
                        line='CALL '+c['op']+' '+str(c['selected'])+' status='+str(status)
                        if c['values'] is not None:
                            line+=payload(c['values'])
                        lines.append(line)
                    if selected is not None:
                        lines.append('PUT '+str(selected))
        lines.append('RETURN '+str(result))
        lines.append('END refs=3,7,11 frag='+str(c['final_frag'])+' alloc='+str(attempts)+'/'+str(releases)+' calls='+str(calls))
    return ('\n'.join(lines)+'\n').encode()


def argv(c, request, expected):
    return [str(c[k]) for k in ('mode','status','oom','selector','result','initial_frag','final_frag','repeat')]+[
        str(request),str(expected),'fixed-contract']
