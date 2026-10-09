# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import bz2
import os

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class UnmergePhaseSkipTestCase(TestCase):
    """
    dblink._unmerge_phases_to_run() decides whether prerm and postrm need a
    spawn, from environment.bz2 and the hook files ebuild.sh would source.
    """

    installed = {
        "dev-libs/A-1": {"EAPI": "7", "SLOT": "0"},
        "dev-libs/B-1": {"EAPI": "7", "SLOT": "0"},
        "dev-libs/C-1": {"EAPI": "7", "SLOT": "0"},
        "dev-libs/D-1": {"EAPI": "7", "SLOT": "0"},
        "dev-libs/E-1.2.3-r4": {"EAPI": "7", "SLOT": "2/3"},
    }

    # cpv -> the functions its environment.bz2 defines, or None for none.
    environments = {
        "dev-libs/A-1": ("src_install", "xdg_pkg_postrm"),
        "dev-libs/B-1": ("pkg_prerm",),
        "dev-libs/C-1": ("post_pkg_postrm",),
        "dev-libs/D-1": None,
        "dev-libs/E-1.2.3-r4": (),
    }

    def setUp(self):
        self.playground = ResolverPlayground(installed=self.installed)
        self.vardb = self.playground.trees[self.playground.eroot]["vartree"].dbapi
        for cpv, funcs in self.environments.items():
            path = os.path.join(self.vardb.getpath(cpv), "environment.bz2")
            if funcs is None:
                if os.path.exists(path):
                    os.unlink(path)
                continue
            env = "".join(f"{name} () \n{{ \n    :\n}}\n" for name in funcs)
            with open(path, "wb") as f:
                f.write(bz2.compress(env.encode()))

    def tearDown(self):
        self.playground.cleanup()

    def _abs(self, path):
        return os.path.join(self.playground.eroot, path)

    def _write(self, path, content):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

    def _dblink(self, cpv):
        dblnk = self.vardb._dblink(cpv)
        # Point the hook files at the playground, not at the host.
        dblnk.settings.unlock()
        dblnk.settings["PORTAGE_BASHRC"] = self._abs("bashrc")
        dblnk.settings["PM_EBUILD_HOOK_DIR"] = self._abs("hooks")
        return dblnk

    def assertSkips(self, dblnk, prerm, postrm):
        run = dblnk._unmerge_phases_to_run()
        self.assertEqual("prerm" not in run, prerm)
        self.assertEqual("postrm" not in run, postrm)

    def test_neither_phase_defined(self):
        # xdg_pkg_postrm is defined but not exported as pkg_postrm.
        self.assertSkips(self._dblink("dev-libs/A-1"), True, True)

    def test_phase_function_defined(self):
        self.assertSkips(self._dblink("dev-libs/B-1"), False, True)

    def test_eclass_hook_defined(self):
        self.assertSkips(self._dblink("dev-libs/C-1"), True, False)

    def test_no_environment(self):
        self.assertSkips(self._dblink("dev-libs/D-1"), False, False)

    def test_hook_file_paths(self):
        # ${CATEGORY}/{${PN},${PN}:${SLOT%/*},${P},${PF}}
        dblnk = self._dblink("dev-libs/E-1.2.3-r4")
        dblnk.settings["SLOT"] = "2/3"
        cat_dir = self._abs("hooks/dev-libs")
        self.assertEqual(
            [p for p in dblnk._phase_hook_files() if p.startswith(cat_dir)],
            [
                os.path.join(cat_dir, name)
                for name in ("E", "E:2", "E-1.2.3", "E-1.2.3-r4")
            ],
        )

    def test_hook_file_mentioning_the_phase(self):
        self._write(self._abs("hooks/dev-libs/A"), "pre_pkg_prerm() { :; }\n")
        self.assertSkips(self._dblink("dev-libs/A-1"), False, True)

    def test_bashrc_mentioning_the_phase(self):
        self._write(self._abs("bashrc"), "post_pkg_postrm() { :; }\n")
        self.assertSkips(self._dblink("dev-libs/A-1"), True, False)

    def test_sourced_file(self):
        self._write(
            self._abs("bashrc"),
            '# source anything here\nif true; then\n\t. "/etc/portage/hook.sh"\nfi\n',
        )
        self.assertSkips(self._dblink("dev-libs/A-1"), False, False)

    def test_commented_source(self):
        self._write(self._abs("bashrc"), "# source /etc/portage/hook.sh\n")
        self.assertSkips(self._dblink("dev-libs/A-1"), True, True)
