# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import contextlib
import io

from _emerge._find_deep_system_runtime_deps import _find_deep_system_runtime_deps
from _emerge.main import insert_optional_args, parse_opts
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class MergeWaitScopeTestCase(TestCase):
    """
    Packages selected for merge-wait are merged only while no build jobs are
    running, so each one is a barrier which limits parallelism. Check that
    --merge-wait-scope selects the intended set of packages.
    """

    def testMergeWaitScope(self):
        ebuilds = {
            # In @system, and part of the core toolchain.
            "sys-libs/glibc-1": {
                "EAPI": "8",
                "RDEPEND": "dev-libs/runtime-dep",
            },
            # In @system, but not part of the core toolchain.
            "app-misc/sysextra-1": {
                "EAPI": "8",
            },
            # Reachable from @system only through a runtime dependency.
            "dev-libs/runtime-dep-1": {
                "EAPI": "8",
                "RDEPEND": "dev-libs/deeper-runtime-dep",
            },
            "dev-libs/deeper-runtime-dep-1": {
                "EAPI": "8",
            },
            # Reachable from @system only through a build-time dependency,
            # so it is not a deep *runtime* dep and never gets merge-wait.
            "dev-libs/build-dep-1": {
                "EAPI": "8",
            },
            "app-misc/unrelated-1": {
                "EAPI": "8",
                "DEPEND": "dev-libs/build-dep",
            },
        }

        expected = {
            "deep": {
                "sys-libs/glibc",
                "app-misc/sysextra",
                "dev-libs/runtime-dep",
                "dev-libs/deeper-runtime-dep",
            },
            "system": {"sys-libs/glibc", "app-misc/sysextra"},
            "toolchain": {"sys-libs/glibc"},
            "none": set(),
        }

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            profile={"packages": ["*sys-libs/glibc", "*app-misc/sysextra"]},
        )

        try:
            result = playground.run(
                ["app-misc/unrelated", "@system"], options={"--emptytree": True}
            )
            self.assertTrue(result.success, "depgraph failed")
            graph = result.depgraph._dynamic_config.digraph

            for scope, expected_cps in expected.items():
                found = {
                    pkg.cp
                    for pkg in _find_deep_system_runtime_deps(graph, scope=scope)
                    if pkg.operation == "merge"
                }
                self.assertEqual(found, expected_cps, f"scope={scope}")

            # The default must preserve the historical behavior.
            default = {
                pkg.cp
                for pkg in _find_deep_system_runtime_deps(graph)
                if pkg.operation == "merge"
            }
            self.assertEqual(default, expected["deep"])

            self.assertRaises(
                ValueError, _find_deep_system_runtime_deps, graph, scope="bogus"
            )
        finally:
            playground.cleanup()

    def testMergeWaitScopeOptionParsing(self):
        for scope in ("deep", "system", "toolchain", "none"):
            myopts = parse_opts(["--merge-wait-scope", scope, "@world"], silent=True)[1]
            self.assertEqual(myopts.get("--merge-wait-scope"), scope)

        # The option is unset by default, and the Scheduler falls back to
        # "deep" in that case.
        self.assertNotIn("--merge-wait-scope", parse_opts(["@world"], silent=True)[1])

        # An argument is required, so insert_optional_args must not supply a
        # default one. It has no valid default, and inserting "True" would
        # make argparse reject the command line with a confusing message
        # about a choice the user never typed.
        argv = ["--merge-wait-scope", "@world"]
        self.assertEqual(insert_optional_args(argv), argv)

        for argv in (["--merge-wait-scope"], ["--merge-wait-scope", "@world"]):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertRaises(SystemExit, parse_opts, argv, silent=True)
