#!/usr/bin/env python3
"""Extractor integrity checks only; these are not DP behavior assertions."""
from pathlib import Path
import tempfile
import unittest

from extract_prepared_c import Prepared, function, structure, variable


class ExtractionIntegrity(unittest.TestCase):
    def test_function_is_actual_not_commented_definition(self):
        source = '/*\nint wanted(void) { return 99; }\n*/\nint wanted(void) { return 1; }\n'
        self.assertEqual(function(source, 'wanted'), 'int wanted(void) { return 1; }\n')

    def test_body_braces_in_comments_literals_preserve_bytes(self):
        actual = 'static int wanted(void) {\n /* } */\n const char *s="\\\"}"; // }\n return s[0] == \'}\';\n}\n'
        self.assertEqual(function(actual + 'int later(void) { return 2; }\n', 'wanted'), actual)

    def test_preprocessor_branches_are_not_reimplemented(self):
        actual = 'int wanted(void) {\n#if REAL_BRANCH\n return 1;\n#else\n return 2;\n#endif\n}\n'
        self.assertEqual(function(actual, 'wanted'), actual)

    def test_split_return_type_preserves_original_bytes(self):
        for separator in ('\n', '\r\n'):
            actual = 'static void' + separator + 'wanted(void *p) { (void)p; }\n'
            self.assertEqual(function(actual, 'wanted'), actual)

    def test_split_return_type_still_rejects_ambiguity_and_prototype(self):
        actual = 'static void\nwanted(void *p) { (void)p; }\n'
        self.assertEqual(function('static void wanted(void *p);\n' + actual, 'wanted'), actual)
        with self.assertRaises(ValueError):
            function(actual + 'void wanted(void *p) { (void)p; }\n', 'wanted')

    def test_missing_or_ambiguous_definition_is_rejected(self):
        with self.assertRaises(ValueError):
            function('int different(void) { return 0; }\n', 'wanted')
        with self.assertRaises(ValueError):
            function('int wanted(void) { return 0; }\nint wanted(void) { return 1; }\n', 'wanted')

    def test_struct_and_initializer_ignore_comment_decoys(self):
        self.assertEqual(structure('/*\nstruct actual { int bad; };\n*/\nstruct actual { int good; };\n', 'actual'),
                         'struct actual { int good; };\n')
        self.assertEqual(variable('/*\nstatic struct ops wanted = { .bad = 0 };\n*/\nstatic struct ops wanted = { .good = 1 };\n', 'wanted'),
                         'static struct ops wanted = { .good = 1 };\n')

    def test_source_mutation_after_extraction_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='nss-dp-extractor-check-') as directory:
            path = Path(directory) / 'actual.c'
            path.write_text('int wanted(void) { return 0; }\n')
            prepared = Prepared(directory)
            prepared.function('actual.c', 'wanted')
            path.write_text('int wanted(void) { return 1; }\n')
            with self.assertRaisesRegex(ValueError, 'changed during host run'):
                prepared.manifest()

    def test_unchanged_input_has_source_and_exact_definition_hashes(self):
        with tempfile.TemporaryDirectory(prefix='nss-dp-extractor-check-') as directory:
            path = Path(directory) / 'actual.c'
            path.write_text('/* original */\nint wanted(void) { return 0; }\n')
            prepared = Prepared(directory)
            prepared.function('actual.c', 'wanted')
            manifest = prepared.manifest()
            self.assertEqual(len(manifest['sources']), 1)
            self.assertEqual(len(manifest['extracted_definitions']), 1)
            self.assertNotEqual(manifest['sources'][0]['sha256'], manifest['extracted_definitions'][0]['sha256'])


if __name__ == '__main__':
    unittest.main()
