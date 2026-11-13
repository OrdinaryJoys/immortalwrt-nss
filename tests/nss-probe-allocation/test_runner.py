#!/usr/bin/env python3
"""Small, disk-free tests of extraction and the evidence acceptance rules."""
import json
from subprocess import CompletedProcess
import sys
import unittest

sys.dont_write_bytecode = True
import run


class ExtractionTests(unittest.TestCase):
    def test_comments_strings_and_call_sites_are_not_definitions(self):
        body = '''static int probe(int x)
{
    const char *s = "} /* { */";
    /* } int probe(void) { */
    if (x) { return '{'; }
    // }
    return s[0];
}'''
        text = '/* int probe(void) { } */\nvoid other(void) { probe(0); }\n' + body
        self.assertEqual(run.extract(text, "probe"), (body, 3))

    def test_preprocessor_branches_stay_verbatim(self):
        text = 'int probe(void) {\n#if FEATURE\nreturn 1;\n#else\nreturn 0;\n#endif\n}'
        self.assertEqual(run.extract(text, "probe")[0], text)

    def test_missing_duplicate_and_truncated_functions_rejected(self):
        for text in ('int other(void) {}', 'int probe(void) {',
                     'int probe(void) {}\nint probe(void) {}'):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                run.extract(text, "probe")

    def test_mutations_must_have_one_anchor(self):
        self.assertEqual(run.replace_once("abc", "b", "z"), "azc")
        for text in ("ac", "abbc"):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                run.replace_once(text, "b", "z")

    def test_bounds_are_backend_specific_and_fail_closed(self):
        header = '''#if defined(NSS_HAL_IPQ807x_SUPPORT) || defined(OTHER)
#define NSS_MAX_IRQ_PER_CORE 10 /* note */
#elif defined(OLDER)
#define NSS_MAX_IRQ_PER_CORE 8
#endif
#define NSS_MAX_CLIENTS 12
#define NSS_N2H_DESC_RING_NUM 15
'''
        self.assertEqual(run.bounds(header)["NSS_MAX_IRQ_PER_CORE"], 10)
        with self.assertRaises(RuntimeError):
            run.bounds(header.replace("CORE 10", "CORE 11"))


class RejectionTests(unittest.TestCase):
    def test_only_exact_runtime_assertion_is_a_killed_control(self):
        stderr = 'NSS_ASSERT expected case=dummy-oom core=0 dt=1\n'
        good = CompletedProcess([], 86, '', stderr)
        self.assertTrue(run.expected_rejection(good, 'expected', 'dummy-oom', 0, 1))
        invalid = [CompletedProcess([], rc, '', stderr) for rc in (0, 1, -6, -11, 124)]
        invalid += [CompletedProcess([], 86, 'unexpected output', stderr),
                    CompletedProcess([], 86, '', stderr.replace('expected', 'wrong')),
                    CompletedProcess([], 86, '', stderr + 'AddressSanitizer error\n'),
                    CompletedProcess([], 86, '', stderr.replace('core=0', 'core=1'))]
        for proc in invalid:
            with self.subTest(proc=proc):
                self.assertFalse(run.expected_rejection(proc, 'expected', 'dummy-oom', 0, 1))


class BindingTests(unittest.TestCase):
    def test_identical_snapshot_is_accepted(self):
        before = {'fixture.c': {'bytes': 3, 'sha256': run.sha256(b'old')}}
        run.unchanged(before, dict(before), 'test assets')

    def test_changed_asset_or_compiler_content_is_rejected(self):
        for name in ('run.py', 'fixture.c', 'actual-functions.inc', 'probe-test', '/compiler'):
            before = {name: {'bytes': 3, 'sha256': run.sha256(b'old')}}
            after = {name: {'bytes': 3, 'sha256': run.sha256(b'new')}}
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'changed during the run'):
                run.unchanged(before, after, name)

    def test_asset_addition_and_removal_are_rejected(self):
        before = {'fixture.c': {'bytes': 3, 'sha256': run.sha256(b'old')}}
        for after in ({}, dict(before, unexpected={'bytes': 0, 'sha256': run.sha256(b'')})):
            with self.subTest(after=after), self.assertRaises(RuntimeError):
                run.unchanged(before, after, 'test asset set')


def rows(trace='lock,alloc,common,free-local,unlock', state=None):
    return [dict(dt=1, core=0, case='common-fail', phase=phase, oom=0, closed=0,
                 ret=-14, trace=trace if phase == 'probe' else 'host-devres-release',
                 allocs=1, local_frees=1, checks=20, state=state or [1, 2, 3])
            for phase in ('probe', 'host-failure-boundary')]


def parsed(items):
    return run.observations('\n'.join(json.dumps(row) for row in items))


class DifferentialTests(unittest.TestCase):
    def test_only_allocation_and_local_free_are_normalized(self):
        old = rows('lock,common,unlock')
        for row in old:
            row.update(allocs=0, local_frees=0, checks=10)
        self.assertEqual(len(run.compare(parsed(old), parsed(rows()))), 2)

    def test_state_errno_and_event_changes_are_rejected(self):
        for field, value in [('state', [1, 2, 4]), ('ret', 0),
                             ('trace', 'lock,common,unmap-n,unlock')]:
            changed = rows()
            changed[0][field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                run.compare(parsed(rows()), parsed(changed))

    def test_event_reordering_is_rejected(self):
        with self.assertRaises(RuntimeError):
            run.compare(parsed(rows('lock,clock,meminfo,unlock')),
                        parsed(rows('lock,meminfo,clock,unlock')))

    def test_empty_duplicate_and_missing_phase_are_rejected(self):
        for data in ([], rows() + rows(), rows()[:1]):
            with self.subTest(data=data), self.assertRaises(RuntimeError):
                parsed(data)

    def test_mismatched_case_sets_are_rejected(self):
        changed = rows()
        for row in changed:
            row['case'] = 'other-case'
        with self.assertRaises(RuntimeError):
            run.compare(parsed(rows()), parsed(changed))

    def test_no_non_oom_comparisons_is_an_error(self):
        data = rows()
        for row in data:
            row['oom'] = 1
        with self.assertRaises(RuntimeError):
            run.compare(parsed(data), parsed(data))


if __name__ == '__main__':
    unittest.main()
