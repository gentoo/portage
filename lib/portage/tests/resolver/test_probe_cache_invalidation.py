# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from _emerge.Dependency import Dependency


class ProbeCacheInvalidationTestCase(TestCase):
    ebuilds = {
        "dev-libs/A-1": {"EAPI": "8"},
        "dev-libs/B-1": {"EAPI": "8"},
        "dev-libs/Z-1": {"EAPI": "8", "RDEPEND": "|| ( dev-libs/A dev-libs/B )"},
    }

    def testGraphChanges(self):
        """
        _select_atoms_probe() prefers an any-of choice already in the graph,
        so its result has to follow packages being removed and added.
        """
        playground = ResolverPlayground(ebuilds=self.ebuilds)
        try:
            dg = playground.run(
                ["dev-libs/Z", "dev-libs/B"], {"--pretend": True}
            ).depgraph
            pkgs = {
                pkg.cp: pkg for pkg in dg._dynamic_config.digraph if hasattr(pkg, "cp")
            }
            z, b = pkgs["dev-libs/Z"], pkgs["dev-libs/B"]

            self.assertEqual(dg._select_atoms_probe(z.root, z), {"dev-libs/B"})
            dg._remove_pkg(b)
            self.assertEqual(dg._select_atoms_probe(z.root, z), {"dev-libs/A"})
            dg._add_pkg(b, Dependency(atom=b.slot_atom, root=b.root, depth=0))
            self.assertEqual(dg._select_atoms_probe(z.root, z), {"dev-libs/B"})
        finally:
            playground.cleanup()

    def testUseChange(self):
        """
        _slot_operator_update_probe() reads the USE of the replacement
        parent, so its result has to follow autounmask USE changes.
        """
        ebuilds = {
            "dev-libs/C-1": {"EAPI": "8", "SLOT": "0/1"},
            "dev-libs/C-2": {"EAPI": "8", "SLOT": "0/2"},
            "app-misc/P-1": {
                "EAPI": "8",
                "IUSE": "foo",
                "RDEPEND": "foo? ( dev-libs/C:= ) !foo? ( <dev-libs/C-2:= )",
            },
        }
        installed = {
            "dev-libs/C-1": {"EAPI": "8", "SLOT": "0/1"},
            "app-misc/P-1": {
                "EAPI": "8",
                "IUSE": "foo",
                "RDEPEND": "<dev-libs/C-2:0/1=",
            },
        }
        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, world=["app-misc/P"]
        )
        try:
            dg = playground.run(
                ["@world"], {"--update": True, "--deep": True, "--pretend": True}
            ).depgraph
            dep = next(
                dep
                for deps in dg._dynamic_config._slot_operator_deps.values()
                for dep in deps
                if dep.parent.installed
            )
            ebuild = next(dg._iter_similar_available(dep.parent, dep.parent.slot_atom))

            self.assertIsNone(dg._slot_operator_update_probe(dep))
            dg._pkg_use_enabled(ebuild, target_use={"foo": True})
            self.assertIsNotNone(dg._slot_operator_update_probe(dep))
        finally:
            playground.cleanup()

    def testDebug(self):
        """
        With --debug the probes always run, keeping their debug output.
        """
        playground = ResolverPlayground(ebuilds=self.ebuilds)
        try:
            for options, cached in (({}, True), ({"--debug": True}, False)):
                options["--pretend"] = True
                dg = playground.run(["dev-libs/Z"], options).depgraph
                z = next(
                    pkg
                    for pkg in dg._dynamic_config.digraph
                    if getattr(pkg, "cp", None) == "dev-libs/Z"
                )
                dg._select_atoms_probe(z.root, z)
                self.assertEqual(
                    bool(dg._dynamic_config._select_atoms_probe_cache), cached
                )
        finally:
            playground.cleanup()
