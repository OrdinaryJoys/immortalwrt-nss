#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#define RPC_SID_LEN 32
#define ARRAY_SIZE(v) (sizeof(v)/sizeof((v)[0]))
#define LOG_ERR 3
#define LOG_WARNING 4
#define syslog(...) ((void)0)
static char journal_path[128];
#define RPC_CHECKED_JOURNAL journal_path
HOST_STRUCTURES
static struct checked_transaction checked_current;
static bool checked_journal_blocked;
static char apply_sid[RPC_SID_LEN+1];
static bool checked_hex(const char *,size_t);
static unsigned checks,failures,scenarios,unlink_calls,fd_leaks,unsafe_fifo_open;
static unsigned read_calls,close_calls;
static int fault_mode,journal_fd=-1,entry_kind;
static unsigned long long normal_signature;
static void check(bool ok) { checks++; if (!ok) failures++; }

static int host_open(const char *path,int flags,...)
{
    mode_t mode=0;
    if (flags&O_CREAT) { va_list ap; va_start(ap,flags); mode=(mode_t)va_arg(ap,int); va_end(ap); }
    if (fault_mode==7) { errno=EACCES; return -1; }
    if (entry_kind==4 && !(flags&O_NONBLOCK)) {
        unsafe_fifo_open++; errno=EAGAIN; return -1;
    }
    int fd=open(path,flags,mode);
    if (fd>=0) {
        if (journal_fd>=0) fd_leaks++;
        journal_fd=fd;
    }
    return fd;
}
static ssize_t host_read(int fd,void *data,size_t bytes)
{
    read_calls++;
    if (fault_mode==1 && bytes>1) bytes=1;
    if (fault_mode==2 && read_calls==1) { errno=EINTR; return -1; }
    if (fault_mode==3) { errno=EIO; return -1; }
    if (fault_mode==4) return 0;
    return read(fd,data,bytes);
}
static int host_close(int fd)
{
    close_calls++;
    if (journal_fd!=fd) fd_leaks++;
    journal_fd=-1;
    int result=close(fd);
    if (fault_mode==5) { errno=EINTR; return -1; }
    return result;
}
static int host_fstat(int fd,struct stat *s)
{
    if (fault_mode==6) { errno=EIO; return -1; }
    return fstat(fd,s);
}
static int host_unlink(const char *path)
{
    unlink_calls++;
    if (fault_mode==8) { errno=EACCES; return -1; }
    return unlink(path);
}
#define open host_open
#define read host_read
#define close host_close
#define fstat host_fstat
#define unlink host_unlink
HOST_FUNCTIONS
#undef open
#undef read
#undef close
#undef fstat
#undef unlink

struct case_info { const char *path; int expected,kind,fault; unsigned files,cleanup,normal; };
static const struct case_info cases[]={
HOST_CASES
};
static void copy_file(const char *from,const char *to)
{
    FILE *a=fopen(from,"rb"),*b=fopen(to,"wb");
    if (!a||!b) abort();
    char data[4096]; size_t n;
    while ((n=fread(data,1,sizeof(data),a))) if (fwrite(data,1,n,b)!=n) abort();
    if (ferror(a)||fclose(a)||fclose(b)) abort();
}
static void reset_state(void)
{
    memset(&checked_current,0,sizeof(checked_current)); memset(apply_sid,0,sizeof(apply_sid));
    checked_journal_blocked=false; unlink_calls=fd_leaks=unsafe_fifo_open=read_calls=close_calls=0;
    fault_mode=0; journal_fd=-1; entry_kind=0;
}
static void one_case(const char *corpus,const struct case_info *test)
{
    char path[PATH_MAX],target[PATH_MAX],tmp[PATH_MAX];
    if (snprintf(path,sizeof(path),"%s/%s",corpus,test->path)>=(int)sizeof(path)) abort();
    strcpy(tmp,"/tmp/ax6-journal-test-XXXXXX");
    if (!mkdtemp(tmp)) abort();
    if (snprintf(journal_path,sizeof(journal_path),"%s/checked.journal",tmp)>=(int)sizeof(journal_path)) abort();
    if (snprintf(target,sizeof(target),"%s/target",tmp)>=(int)sizeof(target)) abort();
    if (test->kind==2) { copy_file(path,target); if (symlink(target,journal_path)) abort(); }
    else if (test->kind==3) { if (mkdir(journal_path,0700)) abort(); }
    else if (test->kind==4) { if (mkfifo(journal_path,0600)) abort(); }
    else if (test->kind!=1) copy_file(path,journal_path);
    reset_state(); fault_mode=test->fault; entry_kind=test->kind;
    checked_journal_load();
    struct stat s;
    bool exists=lstat(journal_path,&s)==0;
    if (test->expected==0) {
        check(!checked_active()); check(!exists);
    } else if (test->expected==1) {
        check(checked_current.state==CHECKED_UNKNOWN); check(!checked_journal_blocked);
        check(checked_current.files==test->files && checked_current.cleanup_pending==(test->cleanup!=0));
        check(!strcmp(checked_current.sid,"cccccccccccccccccccccccccccccccc"));
        check(!strcmp(apply_sid,checked_current.sid)); check(exists && unlink_calls==0);
    } else if (test->expected==2) {
        check(!checked_active()); check(checked_current.state==CHECKED_NONE);
        check(!exists && unlink_calls==1); check(!apply_sid[0]);
    } else {
        check(checked_journal_blocked); check(checked_active());
        check(checked_current.state==CHECKED_NONE && !apply_sid[0]);
        check(exists && (test->fault==8 ? unlink_calls==1 : unlink_calls==0));
    }
    check(fd_leaks==0 && journal_fd==-1 && unsafe_fifo_open==0);
    if (test->normal) normal_signature=normal_signature*131+checked_current.state+checked_current.files+exists;
    if (exists) {
        if (test->kind==3) { if (rmdir(journal_path)) abort(); }
        else if (unlink(journal_path)) abort();
    }
    if (test->kind==2 && unlink(target)) abort();
    if (rmdir(tmp)) abort();
    scenarios++;
}
static void writer_roundtrips(void)
{
    char tmp[]="/tmp/ax6-journal-writer-XXXXXX";
    if (!mkdtemp(tmp)) abort();
    if (snprintf(journal_path,sizeof(journal_path),"%s/checked.journal",tmp)>=(int)sizeof(journal_path)) abort();
    for (int state=CHECKED_APPLYING;state<=CHECKED_UNKNOWN;state++) {
        if (state==CHECKED_CONFIRMED || state==CHECKED_ROLLED_BACK) continue;
        reset_state();
        strcpy(checked_current.id,"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
        strcpy(checked_current.request,"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
        strcpy(checked_current.sid,"cccccccccccccccccccccccccccccccc");
        checked_current.state=state; checked_current.files=2; checked_current.cleanup_pending=true;
        check(checked_journal_write()==0);
        reset_state(); checked_journal_load();
        check(checked_current.state==CHECKED_UNKNOWN && !checked_journal_blocked);
        check(checked_current.files==2 && checked_current.cleanup_pending);
        check(checked_hex(checked_current.id,32)); check(fd_leaks==0 && journal_fd==-1);
        if (unlink(journal_path)) abort();
        scenarios++;
    }
    if (rmdir(tmp)) abort();
}
int main(int argc,char **argv)
{
    if (argc!=2) return 2;
    (void)host_fstat;
    for (size_t i=0;i<ARRAY_SIZE(cases);i++) one_case(argv[1],&cases[i]);
    writer_roundtrips();
    printf("{\"scenarios\":%u,\"checks\":%u,\"failures\":%u,\"normal_signature\":\"%llu\"}\n",
        scenarios,checks,failures,normal_signature);
    return failures?1:0;
}
