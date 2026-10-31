"""Fixed, compile-clean source edits; never modify the Linux mutex model."""


def replace(text, before, after, count):
    if text.count(before) != count:
        raise ValueError('MUTATION_ANCHOR:' + before)
    return text.replace(before, after)


def variants(text):
    guard = 'defined(KERNEL_MODULE) && defined(KVER32)'
    result = {
        'missing-static': replace(text, 'DEFINE_MUTEX(sw_hsl_api_lock);',
                                  'aos_mutex_lock_t sw_hsl_api_lock;', 1),
        'native-runtime-reset': replace(text, 'hsl_api_lock_init(void)\n{',
            'hsl_api_lock_init(void)\n{\n    aos_mutex_lock_init(&sw_hsl_api_lock);', 1),
        'scope-without-kernel': replace(text, guard, 'defined(KVER32)', 2),
        'scope-without-kver32': replace(text, guard, 'defined(KERNEL_MODULE)', 2),
        'scope-includes-user': replace(text, '!defined(USER_MODE) && ', '', 2),
        'scope-includes-standalone': replace(text, ' && !defined(HSL_STANDALONG)', '', 2),
        'destroy-on-init': replace(text, 'hsl_api_lock_init(void)\n{',
                                   'hsl_api_lock_init(void)\n{\n    mutex_destroy(&sw_hsl_api_lock);', 1),
        'legacy-init-missing': replace(text, '    aos_mutex_lock_init(&sw_hsl_api_lock);',
                                       '    /* omitted legacy initialization */', 1)
    }
    if any(value == text for value in result.values()):
        raise ValueError('UNCHANGED_MUTANT')
    return result
