/* Complete actual functions/types are inserted. OS storage is an explicit model. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
typedef uint8_t __a_uint8_t;
typedef uint16_t __a_uint16_t;
typedef uint32_t __a_uint32_t;
typedef uint64_t __a_uint64_t;
/* @TYPES@ */
/* @MACRO@ */
/* @GLOBALS@ */
static hsl_dev_t dev_table[SW_MAX_NR_DEV];
static hsl_dev_t dev_snapshot[SW_MAX_NR_DEV];
struct input {const char *name,*flow; a_uint32_t dev,nr,min,flags; int hw,missing,borrow,rounds,steps,faults[3];};
/* @CASES@ */
static const struct input *in;
static char trace[100000];
static size_t trace_len;
static void fail(const char *s) {fprintf(stderr,"SSDK_VLAN %s\n",s);exit(86);}
#define CHECK(c,s) do {if(!(c))fail(s);} while(0)
static void event(const char *fmt,...) __attribute__((format(printf,1,2)));
static void event(const char *fmt,...)
{
    va_list ap;va_start(ap,fmt);int n=vsnprintf(trace+trace_len,sizeof(trace)-trace_len,fmt,ap);va_end(ap);
    CHECK(n>=0 && (size_t)n<sizeof(trace)-trace_len,"TRACE_CAPACITY");trace_len+=(size_t)n;
}
struct block {void *ptr,*snapshot;size_t bytes;int id,kind,live,foreign;};
static struct block blocks[128];
static int nblocks,serial,step_alloc,fault,construct;
static sid_pool_t *saved_pool[SW_MAX_NR_DEV];
static v_array_t *saved_db[SW_MAX_NR_DEV];
static sll_head_t *saved_list[SW_MAX_NR_DEV];
static a_uint32_t capacity;
static size_t pool_bytes(a_uint32_t n)
{return n<=ID_NR_IN_U8 ? ((n+3u)>>2)<<2 : n<=ID_NR_IN_U16 ? ((n+1u)>>1)<<2 : (size_t)n<<2;}
static unsigned pool_width(a_uint32_t n) {return n<=ID_NR_IN_U8 ? ID_SIZE_U8 : n<=ID_NR_IN_U16 ? ID_SIZE_U16 : ID_SIZE_U32;}
static void global_boundary(void)
{
    if(!construct)return;
    for(unsigned d=0;d<SW_MAX_NR_DEV;d++)CHECK(vlan_pool[d]==saved_pool[d] && vlan_db[d]==saved_db[d] &&
                                             vlan_list[d]==saved_list[d],"EARLY_PUBLICATION");
}
static void snapshot_globals(void)
{memcpy(saved_pool,vlan_pool,sizeof(vlan_pool));memcpy(saved_db,vlan_db,sizeof(vlan_db));memcpy(saved_list,vlan_list,sizeof(vlan_list));}
static struct block *find(void *p)
{
    for(int i=0;i<nblocks;i++)if(blocks[i].ptr==p && p)return &blocks[i];
    fail("POINTER_IDENTITY_BEFORE_DEREF");return NULL;
}
static struct block *owned(void *p,int kind,size_t bytes)
{
    struct block *b=find(p);
    CHECK(!b->foreign && b->live && b->kind==kind && b->bytes==bytes,"OWNED_IDENTITY_SHAPE");return b;
}
static int token(void *p) {return p?find(p)->id:0;}
static void expected_alloc(int ordinal,int *kind,size_t *bytes)
{
    if(!strcmp(in->flow,"pool")) {
        CHECK(ordinal<=2,"POOL_ALLOC_COUNT");*kind=ordinal;*bytes=ordinal==1?sizeof(sid_pool_t):pool_bytes(capacity);return;
    }
    if(!strcmp(in->flow,"list")) {
        CHECK(ordinal==1,"LIST_ALLOC_COUNT");*kind=4;
        *bytes=sizeof(sll_head_t)+((in->flags&LL_FIX_NDNR)?sizeof(sll_node_t)*capacity:0);return;
    }
    CHECK(ordinal<=4,"VLAN_ALLOC_COUNT");*kind=ordinal;
    *bytes=ordinal==1?sizeof(sid_pool_t):ordinal==2?pool_bytes(capacity):ordinal==3?
           sizeof(v_array_t)*capacity:sizeof(sll_head_t)+sizeof(sll_node_t)*capacity;
}
static void *kmalloc(size_t bytes,unsigned flags)
{
    global_boundary();CHECK(flags==3,"LINUX_ALLOC_FLAGS");
    CHECK(!construct || !in->borrow,"BORROWED_ALLOCATION");
    int kind;size_t expected;expected_alloc(++step_alloc,&kind,&expected);
    CHECK(bytes==expected,"ALLOC_EXACT_SIZE");CHECK(nblocks<128,"ALLOC_LEDGER_CAPACITY");
    int id=++serial,ok=step_alloc!=fault;event("ALLOC %d %d %zu %d\n",id,kind,bytes,ok);
    if(!ok)return NULL;
    void *p=malloc(bytes);CHECK(p!=NULL,"HOST_ALLOC");
#ifdef STRESS_POISON
    memset(p,0xa5,bytes); /* Deliberately NON-Linux contract strengthening. */
#else
    memset(p,0,bytes); /* Actual Linux allocator requests __GFP_ZERO. */
#endif
    blocks[nblocks++]=(struct block){p,NULL,bytes,id,kind,1,0};return p;
}
#define GFP_KERNEL 1u
#define __GFP_ZERO 2u
static void kfree(void *p)
{
    global_boundary();if(!p)return;struct block *b=find(p);
    CHECK(!b->foreign,"BORROWED_FREE");CHECK(b->live,"FREE_ONCE");b->live=0;event("FREE %d\n",b->id);
    /* Quarantine storage until final ledger checks; this is not a UAF model. */
}
static void *tracked_memset(void *p,int value,size_t bytes)
{
    global_boundary();struct block *b=find(p);CHECK(!b->foreign,"BORROWED_WRITE");
    CHECK(b->live && bytes==b->bytes && value==0,"ZERO_EXACT_EXTENT");event("ZERO %d %zu\n",b->id,bytes);
    return memset(p,value,bytes);
}
/* @OS@ */
#define aos_printk event
/* @BODIES@ */
/* @OLD@ */
static void seed_one(unsigned d,int mask)
{
    unsigned n=capacity && capacity<=4096?capacity:1;
    for(int kind=1;kind<=4;kind++) {
        int wanted=kind<=2?(mask&1):kind==3?(mask&2):(mask&4);
        if(!wanted)continue;
        size_t size=kind==1?sizeof(sid_pool_t):kind==2?pool_bytes(n):kind==3?sizeof(v_array_t)*n:sizeof(sll_head_t)+sizeof(sll_node_t)*n;
        void *p=malloc(size);CHECK(p!=NULL,"HOST_SEED");memset(p,0x5a,size);
        blocks[nblocks++]=(struct block){p,NULL,size,100+(int)d*10+kind,kind,1,1};
        if(kind==1)vlan_pool[d]=p;
        if(kind==2)vlan_pool[d]->id_pool=p;
        if(kind==3)vlan_db[d]=p;
        if(kind==4)vlan_list[d]=p;
    }
}
static void foreign_check(void)
{
    CHECK(!memcmp(dev_table,dev_snapshot,sizeof(dev_table)),"HSL_METADATA_UNCHANGED");
    for(int i=0;i<nblocks;i++)if(blocks[i].foreign)CHECK(blocks[i].live &&
        !memcmp(blocks[i].ptr,blocks[i].snapshot,blocks[i].bytes),"FOREIGN_BYTES_LIVE");
    for(unsigned d=0;d<SW_MAX_NR_DEV;d++)if(d!=in->dev)CHECK(vlan_pool[d]==saved_pool[d] &&
        vlan_db[d]==saved_db[d] && vlan_list[d]==saved_list[d],"PEER_SLOT_IDENTITIES");
}
static void inspect_pool(sid_pool_t *p,int base,a_uint32_t n,a_uint32_t min)
{
    CHECK(owned(p,1,sizeof(*p))->id==base,"POOL_HEADER_ID");
    CHECK(owned(p->id_pool,2,pool_bytes(n))->id==base+1,"POOL_INNER_ID");
    CHECK(p->id_ptr==0 && p->id_nr==n && p->id_min==min && p->id_size==pool_width(n),"POOL_COMPLETE_FIELDS");
    for(unsigned i=0;i<n;i++) {
        unsigned v=p->id_size==1?((a_uint8_t*)p->id_pool)[i]:p->id_size==2?
                   ((a_uint16_t*)p->id_pool)[i]:((a_uint32_t*)p->id_pool)[i];
        CHECK(v==i,"POOL_ID_CONTENTS");
    }
    for(size_t i=(size_t)n*p->id_size;i<pool_bytes(n);i++)CHECK(((a_uint8_t*)p->id_pool)[i]==0,"POOL_TAIL_ZERO");
    event("POOL %d %d %u %u %u %u IDS_OK\n",base,base+1,p->id_ptr,p->id_nr,p->id_min,p->id_size);
}
static void inspect_list(sll_head_t *p,int id,a_uint32_t n,a_uint32_t flags)
{
    size_t size=sizeof(*p)+((flags&LL_FIX_NDNR)?sizeof(sll_node_t)*n:0);
    CHECK(owned(p,4,size)->id==id,"LIST_ID");
    CHECK(p->fst_nd==NULL && p->nd_nr==0 && p->flag==flags && p->nd_cmp==_fal_vlan_entry_cmp &&
          p->nd_dump==_fal_vlan_entry_dump,"LIST_FIELDS_CALLBACKS");
    sll_node_t *nodes=(sll_node_t*)((a_uint8_t*)p+sizeof(*p));
    sll_node_t *current=p->free_nd;
    if(flags&LL_FIX_NDNR)for(unsigned i=n;i>0;i--) {
        CHECK(current==nodes+i-1,"LIST_NODE_IDENTITY_BEFORE_READ");
        CHECK(current->data==NULL && current->next==(i==1?NULL:nodes+i-2),"LIST_COMPLETE_ORDER");current=current->next;
    }
    CHECK(current==NULL,"LIST_TERMINAL");
    v_array_t a={0},b={0};a.entry.vid=7;b.entry.vid=7;
    CHECK(p->nd_cmp(&a,&b)==LL_CMP_EQUAL,"CMP_EQUAL");b.entry.vid=8;
    CHECK(p->nd_cmp(&a,&b)==LL_CMP_SMALLER && p->nd_cmp(&b,&a)==LL_CMP_GREATER,"CMP_ORDER");
    event("LIST %d %u %u REVERSE_NODES_OK CALLBACKS_OK\n",id,n,flags);
    a.entry.mem_ports=0x35;p->nd_dump(&a);
}
static void inspect_vlan(int base)
{
    CHECK(in->dev<SW_MAX_NR_DEV,"DEV_BEFORE_SLOT");unsigned d=in->dev;
    CHECK(owned(vlan_db[d],3,sizeof(v_array_t)*capacity)->id==base+2,"DB_ID");
    for(size_t i=0;i<sizeof(v_array_t)*capacity;i++)CHECK(((unsigned char*)vlan_db[d])[i]==0,"DB_COMPLETE_ZERO");
    inspect_pool(vlan_pool[d],base,capacity,0);inspect_list(vlan_list[d],base+3,capacity,LL_IN_ORDER|LL_FIX_NDNR);
    event("PUBLISH %u %d %d %d\n",d,base,base+2,base+3);
}
static int phase_ret(int fault_index)
{
    if(in->dev>=SW_MAX_NR_DEV)return SW_NOT_INITIALIZED;
    if(in->hw==A_TRUE)return SW_OK;
    if(!capacity || capacity>4096)return SW_FAIL;
    if(in->borrow)return SW_ALREADY_EXIST;
    return fault_index==3?SW_OUT_OF_MEM:fault_index?SW_FAIL:SW_OK;
}
int main(int argc,char **argv)
{
    CHECK(argc==4,"ARGUMENTS");int index=atoi(argv[1]),expected=atoi(argv[2]);
    CHECK(index>=0 && (size_t)index<sizeof(inputs)/sizeof(inputs[0]),"CASE_INDEX");in=&inputs[index];
    capacity=!strcmp(in->flow,"vlan") || !strcmp(in->flow,"old") ? (a_uint16_t)(in->missing?0:in->nr):in->nr;
    for(unsigned d=0;d<SW_MAX_NR_DEV;d++) {
        seed_one(d,d==in->dev?in->borrow:7);dev_table[d].dev_id=d;
        dev_table[d].nr_vlans=(a_uint16_t)(in->missing?0:in->nr);dev_table[d].hw_vlan_query=(a_bool_t)in->hw;
    }
    for(int i=0;i<nblocks;i++) {blocks[i].snapshot=malloc(blocks[i].bytes);CHECK(blocks[i].snapshot!=NULL,"HOST_SNAPSHOT");memcpy(blocks[i].snapshot,blocks[i].ptr,blocks[i].bytes);}
    memcpy(dev_snapshot,dev_table,sizeof(dev_table));
    snapshot_globals();event("TYPE %u %u %u\n",in->nr,capacity,in->dev);
    for(int round=0;round<in->rounds;round++) {
        int success_base=0;
        for(int step=0;step<in->steps;step++) {
            step_alloc=0;fault=in->faults[step];snapshot_globals();construct=1;int start=serial+1;
            event("BEGIN %d %d %d\n",round,step,fault);int ret;
            if(!strcmp(in->flow,"pool")) {
                sid_pool_t *p=sid_pool_creat(capacity,in->min);ret=p?SW_OK:SW_FAIL;
                CHECK(ret==(fault || !capacity?SW_FAIL:SW_OK),"POOL_RETURN");
                if(p) {inspect_pool(p,start,capacity,in->min);sid_pool_destroy(p);}
            } else if(!strcmp(in->flow,"list")) {
                sll_head_t *p=sll_creat(_fal_vlan_entry_cmp,_fal_vlan_entry_dump,in->flags,capacity);ret=p?SW_OK:SW_FAIL;
                CHECK(ret==(fault?SW_FAIL:SW_OK),"LIST_RETURN");
                if(p) {inspect_list(p,start,capacity,in->flags);sll_destroy(p);}
            } else {
                ret=!strcmp(in->flow,"old")?old_vlan_init(in->dev):fal_vlan_init(in->dev);
                CHECK(ret==(success_base && in->hw!=A_TRUE?SW_ALREADY_EXIST:phase_ret(fault)),"VLAN_RETURN");
                if(!ret && in->dev<SW_MAX_NR_DEV && in->hw!=A_TRUE) {
                    if(!success_base)success_base=start;
                    /* MODEL_LEDGER_INJECTION */
                    inspect_vlan(success_base);
                } else if(!success_base)global_boundary();
            }
            construct=0;CHECK(ret==expected || in->steps>1,"SINGLE_RETURN");foreign_check();
            event("RETURN %d\n",ret);
        }
        if(success_base) {
            event("NORMAL_CLEANUP\n");CHECK(fal_vlan_cleanup(in->dev)==SW_OK,"CLEANUP_RETURN");
            CHECK(fal_vlan_cleanup(in->dev)==SW_OK,"CLEANUP_REPEAT");
            CHECK(!vlan_pool[in->dev] && !vlan_db[in->dev] && !vlan_list[in->dev],"CLEANUP_SLOTS");
        }
        for(int i=0;i<nblocks;i++)CHECK(blocks[i].foreign || !blocks[i].live,"NO_NEW_ORPHANS");
        foreign_check();event("ROUND_END %d\n",round);
    }
    for(unsigned d=0;d<SW_MAX_NR_DEV;d++)event("SLOT %u %d %d %d\n",d,token(vlan_pool[d]),token(vlan_db[d]),token(vlan_list[d]));
    event("END OWNERS_CLOSED_FOREIGN_UNCHANGED\n");
    FILE *f=fopen(argv[3],"rb");CHECK(f!=NULL,"EXPECTED_OPEN");char bytes[sizeof(trace)];size_t n=fread(bytes,1,sizeof(bytes),f);
    CHECK(!ferror(f) && feof(f) && fclose(f)==0,"EXPECTED_EXTENT");
    CHECK(n==trace_len && !memcmp(bytes,trace,n),"EXACT_MODEL_TRACE");
    CHECK(fwrite(trace,1,n,stdout)==n,"STDOUT");
    for(int i=0;i<nblocks;i++) {free(blocks[i].snapshot);free(blocks[i].ptr);}return 0;
}
