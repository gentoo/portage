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
