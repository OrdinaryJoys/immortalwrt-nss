import { connect } from 'ubus';
import { readfile, writefile, stat, unlink, mkdir } from 'fs';

assert(index(readfile('/proc/cmdline') || '', 'ax6_rpcd_ram_fixture=1') >= 0,
       'refuse outside explicitly marked disposable RAM-only guest');
assert(readfile('/run/audit/isolation') == 'network=0 storage=0 shares=0\n',
       'RAM-only fixture launcher required');

let bus=connect('/run/audit/ubus.sock');
assert(bus,'bus');
let mode=trim(readfile('/mode'));
let session=bus.call('session','create',{timeout:240});
let sid=session.ubus_rpc_session;
bus.call('session','grant',{ubus_rpc_session:sid,scope:'uci',objects:[['*','*']]});
assert(!bus.error(true),'grant');
let checks=[];
function record(name,ok) {push(checks,{name,ok:!!ok});assert(ok,name);}
function call(method,args) {let result=bus.call('uci',method,args);return {result,error:bus.error(true)};}
function stage(name) {
    writefile('/etc/config/'+name,"config fixture 'sample'\n\toption value 'before'\n");
    let r=call('set',{ubus_rpc_session:sid,config:name,section:'sample',values:{value:'after'}});
    assert(!r.error,'set '+name);
}
function value(name) {return readfile('/etc/config/'+name);}
function apply() {return call('apply',{ubus_rpc_session:sid,rollback:true,timeout:30});}
function action(method) {return call(method,{ubus_rpc_session:sid});}

if(mode!='baseline') {
    stage('auditfixture');
    assert(!call('commit',{ubus_rpc_session:sid,config:'auditfixture'}).error,
           'prepare an existing session with no pending changes');
    system("for d in /var/run/rpcd/uci-*; do [ ! -d \"$d\" ] || : >\"$d/auditfixture\"; done");
    record('empty legacy apply preserves upstream NO_DATA',apply().error==5);
    record('empty legacy apply does not arm an owner',apply().error==5);
}
stage('auditfixture');
let first=call('apply',{ubus_rpc_session:sid,rollback:true,timeout:2});
if(mode=='baseline') {
    system('/bin/busybox sleep 4');
    record('baseline regression witnessed',!first.error&&index(value('auditfixture'),'after')>=0&&apply().error);
    print('DAEMON_RESULT='+sprintf('%J',{mode,checks,boundary:'actual old rootfs binary negative control'})+'\n');
    exit(0);
}
record('clean apply succeeds',!first.error&&index(value('auditfixture'),'after')>=0);
record('legacy snapshot uses tmpfs',!!stat('/var/run/rpcd/snapshot-files/auditfixture'));
record('legacy does not write checked snapshots',!stat('/etc/rpcd/snapshot-files/auditfixture'));
if(mode=='OFF') record('OFF does not create persistent parent',!stat('/etc/rpcd'));
system('/bin/busybox sleep 4');
record('actual timeout restores config',index(value('auditfixture'),'before')>=0);
record('next apply succeeds',!apply().error);
record('pending owner rejects unchecked apply',!!call('apply',{ubus_rpc_session:sid,rollback:false}).error);
record('normal confirm succeeds',!action('confirm').error);
record('confirm preserves committed config',index(value('auditfixture'),'after')>=0);
for(let fault in ['mkdir','copy']) {
    stage('auditfixture');writefile('/run/audit/fault',fault);
    let r=apply();writefile('/run/audit/fault','');
    record(fault+' rejected before commit',!!r.error&&index(value('auditfixture'),'before')>=0);
    record(fault+' retry apply',!apply().error);
    record(fault+' retry rollback',!action('rollback').error&&index(value('auditfixture'),'before')>=0);
}
stage('auditfixture');writefile('/run/audit/fault','commit');
let failed=apply();writefile('/run/audit/fault','');
record('commit error is not success',!!failed.error);
record('commit failure rollback retries',!action('rollback').error);
stage('auditfixture');record('restore failure setup',!apply().error);
writefile('/run/audit/fault','restore');
let restore=action('rollback');writefile('/run/audit/fault','');
record('restore failure retains snapshot',!!restore.error&&!!stat('/var/run/rpcd/snapshot-files/auditfixture'));
record('restore failure retains owner',!!apply().error);
record('restore retry completes',!action('rollback').error&&index(value('auditfixture'),'before')>=0);
stage('auditfixture');stage('auditfixture2');record('two-file snapshot setup',!apply().error);
let missing=readfile('/var/run/rpcd/snapshot-files/auditfixture2');
unlink('/var/run/rpcd/snapshot-files/auditfixture2');
record('missing one snapshot cannot report rollback success',!!action('rollback').error);
writefile('/var/run/rpcd/snapshot-files/auditfixture2',missing);
record('missing snapshot retry succeeds',!action('rollback').error);
let capability=call('checked',{command:'capabilities'});
if(mode=='OFF') record('checked remains disabled',!!capability.error);
else {
    record('checked remains available only in ON test',!capability.error);
    stage('auditfixture');
    let r=call('checked',{command:'apply',ubus_rpc_session:sid,request:'0123456789abcdef0123456789abcdef',timeout:30});
    record('checked apply pending',!r.error&&r.result.state=='pending');
    record('checked uses own persistent snapshot',!!stat('/etc/rpcd/snapshot-files/auditfixture')&&!stat('/var/run/rpcd/snapshot-files/auditfixture'));
    let token=r.result.token;
    let rolled=call('checked',{command:'rollback',token});
    record('checked rollback terminal result',!rolled.error&&rolled.result.state=='rolled_back'&&index(value('auditfixture'),'before')>=0);
}
print('DAEMON_RESULT='+sprintf('%J',{mode,checks,boundary:'real candidate ARM64 daemon and stock ubus/UCI libraries, RAM-only generic kernel; not AX6 or durable media'})+'\n');
