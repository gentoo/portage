# Copyright 2011-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from itertools import chain

import os
from portage.const import PORTAGE_PYM_PATH, PORTAGE_PYM_PACKAGES
from portage.tests import TestCase


class ImportModulesTestCase(TestCase):
    def testImportModules(self):
        expected_failures = frozenset(())

        iters = (
            self._iter_modules(os.path.join(PORTAGE_PYM_PATH, x))
            for x in PORTAGE_PYM_PACKAGES
        )
        for mod in chain(*iters):
            try:
                __import__(mod)
            except ImportError as e:
                if mod not in expected_failures:
                    self.assertTrue(False, f"failed to import '{mod}': {e}")
                del e

    def _iter_modules(self, base_dir):
        for parent, dirs, files in os.walk(base_dir):
            if isinstance(parent, bytes):
                parent = parent.decode("utf-8", "strict")
            parent_mod = parent[len(PORTAGE_PYM_PATH) + 1 :]
            parent_mod = parent_mod.replace("/", ".")
            for x in files:
                if isinstance(x, bytes):
                    x = x.decode("utf-8", "strict")
                if x[-3:] != ".py":
                    continue
                x = x[:-3]
                if x[-8:] == "__init__":
                    x = parent_mod
                else:
                    x = parent_mod + "." + x
                yield x
