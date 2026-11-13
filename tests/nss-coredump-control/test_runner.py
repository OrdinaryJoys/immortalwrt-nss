#!/usr/bin/env python3
"""Disk-free extractor and exact-runtime-oracle unit tests."""
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
import run


class ExtractionTests(unittest.TestCase):
    def test_literals_comments_and_prototypes(self):
        body = '''static int fn(int x)
{
    const char *s = "} /* { */";
    /* } int fn(void) { */
    if (x) { return '{'; }
    return s[0];
}'''
        source = "int fn(int x);\n/* int fn(void) {} */\n" + body
        self.assertEqual(run.extract(source, "fn"), (body, 3))

    def test_missing_duplicate_unclosed(self):
        for source in ("int other(void) {}", "int fn(void) {",
                       "int fn(void) {}\nint fn(void) {}"):
            with self.subTest(source=source), self.assertRaises(RuntimeError):
                run.extract(source, "fn")

    def test_exact_mutation_anchor(self):
        self.assertEqual(run.replace_once("abc", "b", "z"), "azc")
        for source in ("ac", "abbc"):
            with self.assertRaises(RuntimeError):
                run.replace_once(source, "b", "z")


class RuntimeOracleTests(unittest.TestCase):
    def test_exact_expected_runtime_failure(self):
        errors = ["empty-live:sends"]
        stdout = run.expected_output(errors)
        self.assertTrue(run.accepted(subprocess.CompletedProcess([], 1, stdout, ""), errors))
        for status, out, err in [(0, stdout, ""), (-6, stdout, ""), (-11, stdout, ""),
                                 (1, stdout + "extra\n", ""), (1, stdout, "sanitizer\n"),
                                 (1, stdout.replace("sends", "wrong"), ""), (124, stdout, "")]:
            with self.subTest(status=status, out=out, err=err):
                self.assertFalse(run.accepted(subprocess.CompletedProcess([], status, out, err), errors))

    def test_positive_requires_summary_and_clean_stderr(self):
        self.assertTrue(run.accepted(subprocess.CompletedProcess([], 0, run.expected_output([]), ""), []))
        self.assertFalse(run.accepted(subprocess.CompletedProcess([], 0, "", ""), []))
        self.assertFalse(run.accepted(subprocess.CompletedProcess([], 0, run.expected_output([]), "warning"), []))


if __name__ == "__main__":
    unittest.main()
