#!/usr/bin/env python3
"""DRV extraction-specific integrity tests, not kernel behavior tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

from extract_prepared_c import Prepared

spec=importlib.util.spec_from_file_location('drv_runner',Path(__file__).with_name('test-nss-drv-containment.py'))
runner=importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)


class DriverExtraction(unittest.TestCase):
    def test_actual_private_declaration_ignores_comment_decoy(self):
        with tempfile.TemporaryDirectory(prefix='drv-declaration-') as directory:
            text='/*\nstatic bool closed = true;\n*/\nstatic bool closed;\n'
            Path(directory,'actual.c').write_text(text); prepared=Prepared(directory)
            self.assertEqual(runner.actual_declaration(prepared,'actual.c','closed'),'static bool closed;\n')
            self.assertEqual(prepared.extracted[0]['declaration'],'closed')

    def test_private_declaration_missing_or_ambiguous_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='drv-declaration-') as directory:
            source=Path(directory,'actual.c'); source.write_text('static bool other;\n')
            with self.assertRaises(ValueError): runner.actual_declaration(Prepared(directory),'actual.c','closed')
            source.write_text('static bool closed;\nstatic bool closed;\n')
            with self.assertRaises(ValueError): runner.actual_declaration(Prepared(directory),'actual.c','closed')

    def test_whole_common_unit_substitution_removes_only_include_lines(self):
        source='#include "actual.h"\nstatic bool actual_closed;\n#ifdef ACTUAL_GUARD\nint actual(void) { return actual_closed; }\n#endif\n'
        self.assertEqual(runner.no_includes(source),'\nstatic bool actual_closed;\n#ifdef ACTUAL_GUARD\nint actual(void) { return actual_closed; }\n#endif\n')


if __name__=='__main__': unittest.main()
