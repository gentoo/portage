# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import subprocess
import sys

import portage
from portage import _unicode_decode, os
from portage.const import (
    PORTAGE_PYM_PATH,
    USER_CONFIG_PATH,
    SUPPORTED_GENTOO_BINPKG_FORMATS,
)
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs
from portage.output import colorize


# We test the buildpkg functionality at a basic level with all binary package formats,
# but avoid repeating the same tests for each format to avoid redundancy (just use gpkg / the fastest).
class BuildpkgTestCase(TestCase):
    """
    Test suite for binary package creation using the 'buildpkg' feature in Portage.

    This class focuses on verifying the correct behavior of binary package
    creation in various scenarios, including:

    - Basic binary package creation with the 'buildpkg' feature enabled.
    - Handling of packages with RESTRICT=bindist.
    - The 'suppress-bindist-buildpkg' feature, which prevents binary package
        creation for packages with RESTRICT=bindist.
    - Integration between 'suppress-bindist-buildpkg' and package installation.

    The tests use a ResolverPlayground to simulate a Portage environment and
    assert that binary packages are created or not created as expected based
    on the configuration and package restrictions.
    """

    def testBasicBuildpkg(self):
        """
        Test basic binary package creation with FEATURES=buildpkg flag.
        Verify that binary packages are actually created.
        """
        debug = False

        from portage.tests.emerge.conftest import _INSTALL_SOMETHING

        ebuilds = {
            "dev-libs/test-basic-1::test": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "x86",
                "MISC_CONTENT": _INSTALL_SOMETHING,
            },
        }

        for binpkg_format in SUPPORTED_GENTOO_BINPKG_FORMATS:
            with self.subTest(binpkg_format=binpkg_format):
                print(
                    colorize("HILITE", f"Testing basic buildpkg with {binpkg_format}"),
                    end=" ... ",
                )
                sys.stdout.flush()

                user_config = {
                    "make.conf": (
                        f'BINPKG_FORMAT="{binpkg_format}"',
                        'FEATURES="buildpkg"',
                    ),
                }

                playground = ResolverPlayground(
                    ebuilds=ebuilds, user_config=user_config, debug=debug
                )
                try:
                    self._run_buildpkg_test(
                        playground,
                        "dev-libs/test-basic",
                        expected_binpkg=True,
                        binpkg_format=binpkg_format,
                    )

                finally:
                    playground.cleanup()

    def testBuildpkgWithRestrictBindist(self):
        """
        Test binary package creation with RESTRICT=bindist packages.
        This should always create a binary package, even if the package
        has restricted bindist.
        """
        debug = False

        from portage.tests.emerge.conftest import _INSTALL_SOMETHING

        ebuilds = {
            "dev-libs/test-bindist-1::test": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "x86",
                "RESTRICT": "bindist",
                "MISC_CONTENT": _INSTALL_SOMETHING,
            },
        }

        binpkg_format = "gpkg"
        with self.subTest(binpkg_format=binpkg_format):
            print(
                colorize("HILITE", f"Testing RESTRICT=bindist with {binpkg_format}"),
                end=" ... ",
            )
            sys.stdout.flush()

            user_config = {
                "make.conf": (
                    f'BINPKG_FORMAT="{binpkg_format}"',
                    'FEATURES="buildpkg"',
                ),
            }

            playground = ResolverPlayground(
                ebuilds=ebuilds, user_config=user_config, debug=debug
            )
            try:
                self._run_buildpkg_test(
                    playground,
                    "dev-libs/test-bindist",
                    expected_binpkg=True,  # Should create binpkg
                    binpkg_format=binpkg_format,
                )

            finally:
                playground.cleanup()

    def testSuppressBindistBuildpkgFeature(self):
        """
        Test that suppress-bindist-buildpkg feature prevents creation of binary packages
        for packages with RESTRICT=bindist.
        """
        debug = False

        from portage.tests.emerge.conftest import _INSTALL_SOMETHING

        ebuilds = {
            "dev-libs/test-suppress-1::test": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "x86",
                "RESTRICT": "bindist",
                "MISC_CONTENT": _INSTALL_SOMETHING,
            },
            "dev-libs/test-normal-1::test": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "x86",
                "MISC_CONTENT": _INSTALL_SOMETHING,
            },
        }

        binpkg_format = "gpkg"
        with self.subTest(binpkg_format=binpkg_format):
            print(
                colorize(
                    "HILITE", f"Testing suppress-bindist-buildpkg with {binpkg_format}"
                ),
                end=" ... ",
            )
            sys.stdout.flush()

            user_config = {
                "make.conf": (
                    f'BINPKG_FORMAT="{binpkg_format}"',
                    'FEATURES="buildpkg suppress-bindist-buildpkg"',
                ),
            }

            playground = ResolverPlayground(
                ebuilds=ebuilds, user_config=user_config, debug=debug
            )
            try:
                settings = playground.settings

                self.assertIn(
                    "suppress-bindist-buildpkg",
                    settings.features,
                    "suppress-bindist-buildpkg feature should be enabled",
                )

                self._run_buildpkg_test(
                    playground,
                    "dev-libs/test-suppress",
                    expected_binpkg=False,  # Should NOT create binpkg due to suppress-bindist-buildpkg feature
                    binpkg_format=binpkg_format,
                )

                self._run_buildpkg_test(
                    playground,
                    "dev-libs/test-normal",
                    expected_binpkg=True,  # Should create binpkg normally, feature has no effect
                    binpkg_format=binpkg_format,
                )

            finally:
                playground.cleanup()

    def testSuppressBindistBuildpkgIntegration(self):
        """
        Test the integration between suppress-bindist-buildpkg feature and
        package installation. Packages with RESTRICT=bindist should still
        be installable when the feature is enabled, without creating binary packages.
        """
        debug = False

        from portage.tests.emerge.conftest import _INSTALL_SOMETHING

        ebuilds = {
            "dev-libs/test-integration-1::test": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "x86",
                "RESTRICT": "bindist",
                "MISC_CONTENT": _INSTALL_SOMETHING,
            },
        }

        user_config = {
            "make.conf": ('FEATURES="suppress-bindist-buildpkg"',),
        }

        playground = ResolverPlayground(
            ebuilds=ebuilds, user_config=user_config, debug=debug
        )
        try:
            settings = playground.settings
            eroot = settings["EROOT"]

            emerge_cmd = self._get_emerge_cmd(playground)
            test_commands = (
                emerge_cmd
                + (
                    "--oneshot",
                    "dev-libs/test-integration",
                ),
            )

            success = self._run_commands(playground, test_commands, debug)
            self.assertTrue(
                success,
                "Without ACCEPT_RESTRICT=-bindist, package with RESTRICT=bindist should be installable with suppress-bindist-buildpkg feature",
            )

            vardb = playground.trees[eroot]["vartree"].dbapi
            self.assertTrue(
                vardb.match("dev-libs/test-integration"),
                "Package should be installed in vardb",
            )

        finally:
            playground.cleanup()

    def testSuppressBindistBuildpkgFeatureDefinition(self):
        """
        Test that suppress-bindist-buildpkg is properly defined in SUPPORTED_FEATURES.
        """
        from portage.const import SUPPORTED_FEATURES

        self.assertIn(
            "suppress-bindist-buildpkg",
            SUPPORTED_FEATURES,
            "suppress-bindist-buildpkg should be in SUPPORTED_FEATURES",
        )

    def _run_buildpkg_test(
        self, playground, package_atom, expected_binpkg, binpkg_format
    ):
        """
        Helper method to run a buildpkg test and verify the results.

        Args:
            playground: ResolverPlayground instance
            package_atom: Package atom to build (e.g., "dev-libs/test-basic")
            expected_binpkg: Whether a binary package should be created
            binpkg_format: Binary package format (xpak or gpkg)
        """
        emerge_cmd = self._get_emerge_cmd(playground)

        test_commands = (
            emerge_cmd
            + (
                "--oneshot",
                package_atom,
            ),
        )

        success = self._run_commands(playground, test_commands, False)
        self.assertTrue(success, f"Emerge command should succeed for {package_atom}")

        binpkg_created = self._check_binpkg_exists(
            playground, package_atom, binpkg_format
        )

        if expected_binpkg:
            self.assertTrue(
                binpkg_created, f"Binary package should be created for {package_atom}"
            )
        else:
            self.assertFalse(
                binpkg_created,
                f"Binary package should NOT be created for {package_atom}",
            )

    def _check_binpkg_exists(self, playground, package_atom, binpkg_format):
        """
        Check if a binary package was created for the given package atom.

        Args:
            playground: ResolverPlayground instance
            package_atom: Package atom to check
            binpkg_format: Binary package format (xpak or gpkg)

        Returns:
            bool: True if binary package exists, False otherwise
        """
        settings = playground.settings
        eroot = settings["EROOT"]
        trees = playground.trees
        bindb = trees[eroot]["bintree"].dbapi

        # Force bintree to update its index
        bindb.bintree.populate(force_reindex=True)

        # Check if package is in binary database
        matches = bindb.match(package_atom)
        if not matches:
            return False

        # Check if actual binary package file exists
        for cpv in matches:
            binpkg_path = bindb.bintree.getname(cpv, allocate_new=False)
            if binpkg_path and os.path.exists(binpkg_path):
                match binpkg_format:
                    case "gpkg":
                        if binpkg_path.endswith(".gpkg.tar"):
                            return True
                    case "xpak":
                        if binpkg_path.endswith((".tbz2", ".xpak")):
                            return True
                    case _:
                        return False

        return False

    def _get_emerge_cmd(self, playground):
        """Get the emerge command for the given playground."""
        portage_python = portage._python_interpreter
        emerge_cmd = (
            portage_python,
            "-b",
            "-Wd",
            os.path.join(str(portage.const.PORTAGE_BIN_PATH), "emerge"),
        )
        return emerge_cmd

    def _run_commands(self, playground, test_commands, debug):
        """
        Run a sequence of commands in the playground environment.

        Args:
            playground: ResolverPlayground instance
            test_commands: Tuple of command tuples to run
            debug: Whether to enable debug output

        Returns:
            bool: True if all commands succeeded, False otherwise
        """
        settings = playground.settings
        eprefix = settings["EPREFIX"]
        fake_bin = os.path.join(eprefix, "bin")
        portage_tmpdir = os.path.join(eprefix, "var", "tmp", "portage")
        user_config_dir = os.path.join(eprefix, USER_CONFIG_PATH)
        var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")

        path = settings.get("PATH")
        if path is not None and not path.strip():
            path = None
        if path is None:
            path = ""
        else:
            path = ":" + path
        path = fake_bin + path

        pythonpath = os.environ.get("PYTHONPATH")
        if pythonpath is not None and not pythonpath.strip():
            pythonpath = None
        if pythonpath is not None and pythonpath.split(":")[0] == PORTAGE_PYM_PATH:
            pass
        else:
            if pythonpath is None:
                pythonpath = ""
            else:
                pythonpath = ":" + pythonpath
            pythonpath = PORTAGE_PYM_PATH + pythonpath

        env = {
            "PORTAGE_OVERRIDE_EPREFIX": eprefix,
            "PATH": path,
            "PORTAGE_PYTHON": portage._python_interpreter,
            "PORTAGE_REPOSITORIES": settings.repositories.config_string(),
            "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE", ""),
            "PYTHONPATH": pythonpath,
            "PORTAGE_INST_GID": str(os.getgid()),
            "PORTAGE_INST_UID": str(os.getuid()),
            "FEATURES": "-pkgdir-index-trusted",
        }

        dirs = [
            playground.distdir,
            fake_bin,
            portage_tmpdir,
            user_config_dir,
            var_cache_edb,
        ]

        true_symlinks = ["chown", "chgrp"]
        needed_binaries = {
            "true": (find_binary("true"), True),
        }

        try:
            for d in dirs:
                ensure_dirs(d)
            for x in true_symlinks:
                true_binary = needed_binaries["true"][0]
                if true_binary:
                    try:
                        os.symlink(true_binary, os.path.join(fake_bin, x))
                    except FileExistsError:
                        pass

            with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
                f.write(b"100")

            if debug:
                stdout = None
            else:
                stdout = subprocess.PIPE

            all_successful = True
            for i, args in enumerate(test_commands):
                if hasattr(args[0], "__call__"):
                    continue

                if isinstance(args[0], dict):
                    local_env = env.copy()
                    local_env.update(args[0])
                    args = args[1:]
                else:
                    local_env = env

                proc = subprocess.Popen(args, env=local_env, stdout=stdout)

                if debug:
                    proc.wait()
                else:
                    output = proc.stdout.readlines()
                    proc.wait()
                    proc.stdout.close()
                    if proc.returncode != os.EX_OK:
                        for line in output:
                            sys.stderr.write(_unicode_decode(line))

                if proc.returncode != os.EX_OK:
                    all_successful = False
                    break

            return all_successful

        except Exception as e:
            print(f"Exception in _run_commands: {e}")
            return False
