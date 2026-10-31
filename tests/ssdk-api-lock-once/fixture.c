/* Second TU. Linux storage/operations are serial models, not target mutex ABI. */
#include "sdk.h"
static _Noreturn void fail(const char *s)
{ fprintf(stderr,"LOCK_ASSERT:%s\n",s); exit(86); }
#define CHECK(c,s) do { if (!(c)) fail(s); } while (0)
void model_init(struct mutex *m)
{ ++m->inits; m->ready=1; m->held=0; m->locks=m->unlocks=0; m->cookie=LOCK_COOKIE; }
void model_lock(struct mutex *m)
{ CHECK(m==&sw_hsl_api_lock && m->ready && !m->held,"MODEL_LOCK"); m->held=1; ++m->locks; }
void model_unlock(struct mutex *m)
{ CHECK(m==&sw_hsl_api_lock && m->ready && m->held,"MODEL_UNLOCK"); m->held=0; ++m->unlocks; }
void model_destroy(struct mutex *m)
{ ++m->destroys; m->ready=0; }
static void preserved(struct mutex before, const char *marker)
{ CHECK(!memcmp(&before,&sw_hsl_api_lock,sizeof(before)),marker); }
static sw_error_t bootstrap_actor(sw_error_t outcome)
{ CHECK(hsl_api_lock_init()==SW_OK,"ACTOR_INIT_RETURN"); return outcome; }
int main(int argc,char **argv)
{
    struct mutex before;
    const char *name;
    unsigned i;
    CHECK(argc==2,"ARGUMENTS"); name=argv[1];
    if (!strcmp(name,"legacy")) {
        CHECK(!EXPECT_NATIVE,"PROFILE");
        CHECK(!sw_hsl_api_lock.ready && !sw_hsl_api_lock.inits,"LEGACY_INITIAL");
        for (i=1;i<=3;++i) {
            CHECK(hsl_api_lock_init()==SW_OK,"LEGACY_RETURN");
            CHECK(sw_hsl_api_lock.ready && !sw_hsl_api_lock.held &&
                  sw_hsl_api_lock.inits==i && !sw_hsl_api_lock.destroys &&
                  sw_hsl_api_lock.cookie==LOCK_COOKIE,"LEGACY_INIT");
            aos_mutex_lock(&sw_hsl_api_lock); aos_mutex_unlock(&sw_hsl_api_lock);
        }
    } else {
        CHECK(EXPECT_NATIVE,"PROFILE");
        CHECK(sw_hsl_api_lock.ready && !sw_hsl_api_lock.held &&
              !sw_hsl_api_lock.inits && !sw_hsl_api_lock.destroys &&
              !sw_hsl_api_lock.locks && !sw_hsl_api_lock.unlocks &&
              sw_hsl_api_lock.cookie==LOCK_COOKIE,"NATIVE_LOAD");
        if (!strcmp(name,"load")) {
            aos_mutex_lock(&sw_hsl_api_lock); aos_mutex_unlock(&sw_hsl_api_lock);
        } else if (!strcmp(name,"repeat")) {
            before=sw_hsl_api_lock;
            for (i=0;i<4;++i) {
                CHECK(hsl_api_lock_init()==SW_OK,"INIT_RETURN"); preserved(before,"REPEAT_PRESERVE");
            }
        } else if (!strcmp(name,"held")) {
            aos_mutex_lock(&sw_hsl_api_lock); before=sw_hsl_api_lock;
            for (i=0;i<3;++i) {
                CHECK(hsl_api_lock_init()==SW_OK,"INIT_RETURN"); preserved(before,"HELD_PRESERVE");
            }
            aos_mutex_unlock(&sw_hsl_api_lock);
        } else if (!strcmp(name,"bootstrap")) {
            const sw_error_t outcomes[]={SW_INIT_ERROR,SW_OK,SW_OUT_OF_MEM,SW_OK};
            aos_mutex_lock(&sw_hsl_api_lock); before=sw_hsl_api_lock;
            for (i=0;i<sizeof(outcomes)/sizeof(outcomes[0]);++i) {
                CHECK(bootstrap_actor(outcomes[i])==outcomes[i],"ACTOR_FIRST_ERROR");
                preserved(before,"BOOTSTRAP_PRESERVE");
            }
            aos_mutex_unlock(&sw_hsl_api_lock);
        } else fail("CASE");
    }
    CHECK(sw_hsl_api_lock.ready && !sw_hsl_api_lock.held &&
          sw_hsl_api_lock.locks==sw_hsl_api_lock.unlocks && !sw_hsl_api_lock.destroys,"FINAL_STATE");
    printf("OK %s\n",name); return 0;
}
