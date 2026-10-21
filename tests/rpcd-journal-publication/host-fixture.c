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
#include <time.h>
#include <unistd.h>
#define RPC_SID_LEN 32
#define LOG_ERR 3
#define syslog(...) ((void)0)
static char directory[128], journal[160], temporary[164], files[160], delta[160];
#define RPC_CHECKED_DIR directory
#define RPC_CHECKED_JOURNAL journal
#define RPC_CHECKED_SNAPSHOT_FILES files
#define RPC_CHECKED_SNAPSHOT_DELTA delta
HOST_STRUCTURES
static struct checked_transaction checked_current;
static bool checked_journal_blocked, publishing;
static bool live[1024];
static unsigned fd_errors, cloexec_errors, unsafe_fifo;
static int fault, kind;
static int host_open(const char *path,int flags,...)
{
    mode_t mode=0;
    if (flags&O_CREAT) {va_list ap;va_start(ap,flags);mode=(mode_t)va_arg(ap,int);va_end(ap);}
    if (publishing && fault==1) {errno=EACCES;return -1;}
    if (publishing && kind==6 && !strcmp(path,temporary) && !(flags&O_EXCL)) {
        unsafe_fifo++;errno=EAGAIN;return -1;
    }
    int fd=open(path,flags,mode);
    if (fd>=0) {
        if (fd>=1024 || live[fd]) abort();
        live[fd]=true;
        if (publishing && !(fcntl(fd,F_GETFD)&FD_CLOEXEC)) cloexec_errors++;
    }
    return fd;
}
static ssize_t host_write(int fd,const void *data,size_t count)
{
    if (fault==2 && count>7) count=7;
    if (fault==3 || fault==9) {errno=EIO;return -1;}
    if (fault==4) {errno=EINTR;return -1;}
    if (fault==5) return 0;
    return write(fd,data,count);
}
static int host_close(int fd)
{
    if (fd<0 || fd>=1024 || !live[fd]) fd_errors++;
    else live[fd]=false;
    int ret=close(fd);
    if (publishing && fault==6) {errno=EINTR;return -1;}
    return ret;
}
static int host_fsync(int fd)
{
    if (fault==7) {errno=EIO;return -1;}
    return fsync(fd);
}
static int host_rename(const char *from,const char *to)
{
    if (fault==8) {errno=EACCES;return -1;}
    return rename(from,to);
}
static int host_unlink(const char *path)
{
    if (publishing && fault==9) {errno=EACCES;return -1;}
    return unlink(path);
}
#define open host_open
#define write host_write
#define close host_close
#define fsync host_fsync
#define rename host_rename
#define unlink host_unlink
HOST_FUNCTIONS
#undef open
#undef write
#undef close
#undef fsync
#undef rename
#undef unlink
int main(int argc,char **argv)
{
    if (argc!=6 || strlen(argv[1])>=sizeof(directory)) return 2;
    strcpy(directory,argv[1]);
    if (snprintf(journal,sizeof(journal),"%s/checked.journal",directory)>=(int)sizeof(journal) ||
        snprintf(temporary,sizeof(temporary),"%s.tmp",journal)>=(int)sizeof(temporary) ||
        snprintf(files,sizeof(files),"%s/snapshot-files/",directory)>=(int)sizeof(files) ||
        snprintf(delta,sizeof(delta),"%s/snapshot-delta/",directory)>=(int)sizeof(delta)) return 2;
    checked_storage_init();
    if (checked_journal_blocked) return 3;
    kind=atoi(argv[2]);fault=atoi(argv[3]);umask((mode_t)strtoul(argv[5],NULL,8));
    strcpy(checked_current.id,"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    strcpy(checked_current.request,"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    strcpy(checked_current.sid,"cccccccccccccccccccccccccccccccc");
    checked_current.state=(enum checked_state)atoi(argv[4]);
    checked_current.files=2;checked_current.cleanup_pending=true;
    publishing=true;
    int result=checked_journal_write();
    unsigned leaks=0;
    for (unsigned i=0;i<sizeof(live)/sizeof(live[0]);i++) leaks+=live[i];
    printf("{\"result\":%d,\"blocked\":%s,\"fd_errors\":%u,\"fd_leaks\":%u,\"cloexec_errors\":%u,\"unsafe_fifo\":%u}\n",
        result,checked_journal_blocked?"true":"false",fd_errors,leaks,cloexec_errors,unsafe_fifo);
    return 0;
}
