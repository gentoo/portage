# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import subprocess

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class QuickpkgDirectMaskInfoTestCase(TestCase):
    def testQuickpkgDirectMaskInfo(self):
        """
        Test bug 986429, where reporting an unsatisfied dep with
        --quickpkg-direct=y crashed with "AttributeError: 'vardbapi'
        object has no attribute 'bintree'", because get_mask_info()
        built a binary Package from a cpv still linked to the vardbapi.
        """
        ebuilds = {
            "dev-libs/A-1": {"EAPI": "8", "KEYWORDS": "x86"},
        }
        installed = {
            "dev-libs/A-1": {"EAPI": "8", "KEYWORDS": "x86"},
        }
        playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
        try:
            # Since ResolverPlayground does not internally support
            # cross-root, test with emerge.
            cross_root = os.path.join(playground.settings["EPREFIX"], "cross_root")
            os.makedirs(cross_root)
            result = subprocess.run(
                [
                    "emerge",
                    f"--root={cross_root}",
                    "--pretend",
                    "--usepkgonly",
                    "--quickpkg-direct=y",
                    "dev-libs/A[foo]",
                ],
                env=playground.settings.environ(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            output = result.stdout.decode(errors="replace")
            try:
                self.assertNotIn("Traceback", output)
                self.assertIn("dev-libs/A-1::test_repo (Missing IUSE: foo)", output)
                self.assertNotEqual(result.returncode, os.EX_OK)
            except Exception:
                print(output)
                raise
        finally:
            playground.cleanup()
