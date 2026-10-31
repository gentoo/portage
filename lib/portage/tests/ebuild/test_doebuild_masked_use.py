# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

import portage
from portage.package.ebuild._ipc.QueryCommand import QueryCommand
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class DoebuildMaskedUseTestCase(TestCase):
    def testDoebuildMaskedUse(self):
        """
        Build and merge an ebuild with MASKED_USE, and check that the ebuild
        environment has the masked flags disabled, and that both the
        resulting USE and MASKED_USE are recorded for the installed package.
        """
        py12 = "python_single_target_python3_12"
        py13 = "python_single_target_python3_13"
        ebuilds = {
            "dev-vcs/git-1": {
                "EAPI": "9-masked-use",
                "IUSE": f"foo perforce {py12} {py13}",
                "MASKED_USE": f"!perforce? ( {py12} {py13} )",
                "MISC_CONTENT": "\n".join(
                    (
                        "S=${WORKDIR}",
                        "src_install() {",
                        "\tuse foo || die",
                        f"\tuse {py13} && die",
                        "}",
                    )
                ),
            }
        }
        user_config = {"make.conf": (f'USE="foo {py13}"',)}

        # Override things that may be unavailable, or may have portability
        # issues when running tests in exotic environments.
        true_symlinks = ("find", "prepstrip", "sed", "scanelf")
        true_binary = portage.process.find_binary("true")
        self.assertEqual(true_binary is None, False, "true command not found")

        playground = ResolverPlayground(ebuilds=ebuilds, user_config=user_config)
        try:
            QueryCommand._db = playground.trees
            root_config = playground.trees[playground.eroot]["root_config"]
            portdb = root_config.trees["porttree"].dbapi
            vardb = root_config.trees["vartree"].dbapi
            settings = portage.config(clone=playground.settings)
            if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
                settings["__PORTAGE_TEST_HARDLINK_LOCKS"] = os.environ[
                    "__PORTAGE_TEST_HARDLINK_LOCKS"
                ]
                settings.backup_changes("__PORTAGE_TEST_HARDLINK_LOCKS")

            settings["PORTAGE_PYTHON"] = portage._python_interpreter
            settings["PORTAGE_QUIET"] = "1"
            settings["PYTHONDONTWRITEBYTECODE"] = os.environ.get(
                "PYTHONDONTWRITEBYTECODE", ""
            )

            fake_bin = os.path.join(settings["EPREFIX"], "bin")
            portage.util.ensure_dirs(fake_bin)
            for x in true_symlinks:
                os.symlink(true_binary, os.path.join(fake_bin, x))

            settings["__PORTAGE_TEST_PATH_OVERRIDE"] = fake_bin
            settings.backup_changes("__PORTAGE_TEST_PATH_OVERRIDE")

            cpv = "dev-vcs/git-1"
            self.assertEqual(
                portage.doebuild(
                    portdb.findname(cpv),
                    "merge",
                    settings=settings,
                    mydbapi=portdb,
                    tree="porttree",
                    vartree=root_config.trees["vartree"],
                    prev_mtimes={},
                ),
                os.EX_OK,
            )

            use, masked_use = vardb.aux_get(cpv, ["USE", "MASKED_USE"])
            self.assertEqual(
                {"foo", "perforce", py12, py13}.intersection(use.split()), {"foo"}
            )
            self.assertEqual(masked_use, ebuilds[cpv]["MASKED_USE"])
        finally:
            playground.cleanup()
            QueryCommand._db = None
