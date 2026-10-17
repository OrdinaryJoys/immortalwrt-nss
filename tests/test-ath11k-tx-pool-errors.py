#!/usr/bin/env python3
"""Compile real prepared TX-prefix/helper statements with modeled pools/locks."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('prepared', type=Path)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--expect-failure', action='store_true')
args = parser.parse_args()
ROOT = args.output
ROOT.mkdir(parents=True, exist_ok=False)
ath = Path('drivers/net/wireless/ath/ath11k')

def run(label, argv, *, cwd=None, data=None):
    result = subprocess.run(argv, cwd=cwd, input=data, capture_output=True, timeout=180)
    (ROOT / (label + '.stdout')).write_bytes(result.stdout)
    (ROOT / (label + '.stderr')).write_bytes(result.stderr)
    return {'argv': argv, 'exit': result.returncode, 'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
            'stderr_sha256': hashlib.sha256(result.stderr).hexdigest()}

stubs = r'''
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
typedef uint32_t u32;
typedef uint8_t u8;
#define DP_TX_IDR_SIZE 64
#define DP_TCL_NUM_RING_MAX 3
struct ieee80211_vif { int value; };
struct ath11k_skb_cb { struct ieee80211_vif *vif; };
struct sk_buff { struct ath11k_skb_cb cb; };
struct ieee80211_tx_status { int unused; };
struct ieee80211_tx_info { int unused; };
struct ath11k { int unused; };
struct ath11k_peer { int unused; };
struct pool_item { int id; struct sk_buff *buf; };
struct dp_tx_ring { int tx_idr_lock, txbuf_idr; struct pool_item idr_pool[DP_TX_IDR_SIZE]; unsigned long idrs[1]; };
struct ath11k_base { struct { struct dp_tx_ring tx_ring[DP_TCL_NUM_RING_MAX]; } dp; };
struct ath11k_dp_htt_wbm_tx_status { u32 msdu_id; };
#define ATH11K_SKB_CB(skb) (&((struct sk_buff *)(skb))->cb)
#define unlikely(x) (x)
#define ath11k_warn(...) ((void)0)
static int locks, consumed;
#define spin_lock_bh(p) do { (void)(p); locks++; } while (0)
#define spin_unlock_bh(p) do { (void)(p); locks--; } while (0)
#define clear_bit(i,p) (*(p) &= ~(1UL << (i)))
#define for_each_set_bit(i,p,n) for ((i)=0;(i)<(n);(i)++) if ((*(p) >> (i)) & 1UL)
static inline void idr_for_each(int *idr, int (*fn)(int,void *,void *), void *vif) { (void)idr; (void)fn; (void)vif; assert(locks == 1); }
'''

def snippet(path, start, end):
    text = path.read_text()
    assert text.count(start) == 1
    position = text.index(start)
    return text[position:text.index(end, position)]

tests = []
for label, tree in [('baseline' if args.expect_failure else 'candidate', args.prepared)]:
    directory = ROOT / ('c-tests-' + label)
    directory.mkdir()
    prefix = snippet(tree / ath / 'dp_tx.c', 'ath11k_dp_tx_htt_tx_complete_buf(struct ath11k_base *ab,', '\tskb_cb = ATH11K_SKB_CB(msdu);')
    tx = stubs + '\nstatic void ' + prefix + '\tconsumed++;\n}\n' + r'''
int main(void) {
    struct ath11k_base ab = {0}; struct dp_tx_ring ring = {0};
    struct sk_buff skb = {0}; struct ath11k_dp_htt_wbm_tx_status ts = {0}; int passed=0;
    for(int i=0;i<DP_TX_IDR_SIZE;i++) ring.idr_pool[i].id=-1;
    ts.msdu_id=5; ring.idr_pool[5].id=5; ring.idr_pool[5].buf=&skb; ring.idrs[0]=1UL<<5;
    consumed=0; ath11k_dp_tx_htt_tx_complete_buf(&ab,&ring,&ts);
    passed += consumed==1 && ring.idr_pool[5].id==-1 && ring.idrs[0]==0 && locks==0;
    consumed=0; ath11k_dp_tx_htt_tx_complete_buf(&ab,&ring,&ts); passed += consumed==0 && locks==0;
    ts.msdu_id=DP_TX_IDR_SIZE; consumed=0; ath11k_dp_tx_htt_tx_complete_buf(&ab,&ring,&ts); passed += consumed==0 && locks==0;
    printf("tx_passed=%d/3\n",passed); return passed==3 ? 0:1;
}
'''
    (directory / 'tx.c').write_text(tx)
    helper = snippet(tree / ath / 'mac.c', 'static ' + ('int' if label == 'baseline' else 'void') + ' ath11k_mac_vif_unref(', 'static void ath11k_mac_op_remove_interface(')
    mac = (tree / ath / 'mac.c').read_text()
    remove = mac[mac.index('static void ath11k_mac_op_remove_interface('):]
    start = remove.index('\tfor (i = 0; i < DP_TCL_NUM_RING_MAX; i++) {')
    block = remove[start:remove.index('\n\t/* Recalc txpower', start)]
    vif = stubs + helper + '\nstatic void remove_pending(struct ath11k_base *ab, struct ieee80211_vif *vif) { int i;\n' + block + '\n}\n' + r'''
int main(void) {
    struct ath11k_base ab={0}; struct ieee80211_vif a={1},b={2};
    struct sk_buff frames[3][3]={0}; int passed=0;
    for(int r=0;r<3;r++) {
        frames[r][0].cb.vif=&a; frames[r][1].cb.vif=&b; frames[r][2].cb.vif=&a;
        int ids[3]={0,17,63};
        for(int j=0;j<3;j++) { ab.dp.tx_ring[r].idrs[0]|=1UL<<ids[j]; ab.dp.tx_ring[r].idr_pool[ids[j]].buf=&frames[r][j]; }
    }
    remove_pending(&ab,&a);
    for(int r=0;r<3;r++) { passed += !frames[r][0].cb.vif; passed += frames[r][1].cb.vif==&b; passed += !frames[r][2].cb.vif; }
    passed += locks==0; remove_pending(&ab,&a); passed += locks==0;
    printf("vif_passed=%d/11\n",passed); return passed==11?0:1;
}
'''
    (directory / 'vif.c').write_text(vif)
    for name in ('tx', 'vif'):
        compile_result = run('compile-' + label + '-' + name, ['clang', '-std=gnu11', '-O0', '-Wall', '-Wextra',
            *(['-Werror'] if label != 'baseline' else []), '-Wno-sign-compare', '-Wno-unused-variable', '-Wno-unused-function', '-Wno-unused-parameter', '-ftrivial-auto-var-init=pattern',
            str(directory / (name + '.c')), '-o', str(directory / name)])
        assert compile_result['exit'] == 0
        execution = run('run-' + label + '-' + name, [str(directory / name)])
        assert execution['exit'] == (1 if label == 'baseline' else 0)
        tests.append({'variant': label, 'component': name, 'compile': compile_result, 'run': execution,
                      'uses_mocks': True, 'limits': 'Extracted source statements, not kernel, DMA, IRQ or concurrent lifetime verification.'})

(ROOT / 'RESULT.json').write_text(json.dumps({
    'at': datetime.now(timezone.utc).isoformat(), 'tests': tests,
    'target_compile': False, 'hardware_test': False,
    'scope': 'Extracted source prefix/helper; not full completion or concurrent lifetime proof.'
}, indent=2) + '\n')
print(json.dumps(tests, indent=2))
