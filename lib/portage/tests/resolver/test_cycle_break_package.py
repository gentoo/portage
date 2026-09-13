# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import portage
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground

from _emerge.Package import Package


class CycleBreakPackageTestCase(TestCase):
    def testCycleBreakIdentity(self):
        """
        A package in a dependency cycle can be merged twice: first as a
        transient instance built with fewer USE flags (here freetype with
        USE=-harfbuzz), and then with the requested flags. Check that the
        two Package instances are distinct and that each is built with
        its own USE flags.
        """
        ebuilds = {
            "media-libs/freetype-1": {
                "DEPEND": "harfbuzz? ( media-libs/harfbuzz )",
                "IUSE": "+harfbuzz",
                "EAPI": "8",
            },
            "media-libs/harfbuzz-1": {
                "DEPEND": "media-libs/freetype",
                "EAPI": "8",
            },
        }

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            root_config = playground.trees[playground.eroot]["root_config"]
            portdb = playground.trees[playground.eroot]["porttree"].dbapi
            cpv = portdb.cp_list("media-libs/freetype")[0]
            metadata = dict(
                zip(
                    Package.metadata_keys,
                    portdb.aux_get(cpv, Package.metadata_keys, myrepo=cpv.repo),
                )
            )

            final = Package(
                built=False,
                cpv=cpv,
                metadata=metadata,
                root_config=root_config,
                type_name="ebuild",
            )
            transient = Package(
                built=False,
                cpv=cpv,
                cycle_use_changes=frozenset([("harfbuzz", False)]),
                metadata=metadata,
                root_config=root_config,
                type_name="ebuild",
            )

            # The two instances must be distinguishable, so that both can
            # be present in the same graph and merge list.
            self.assertEqual(len({final, transient}), 2)

            # The forced USE flags are applied to the build settings.
            settings = portage.config(clone=playground.settings)
            settings.unlock()
            settings.setcpv(final)
            self.assertIn("harfbuzz", settings["PORTAGE_USE"].split())
            settings.setcpv(transient)
            self.assertNotIn("harfbuzz", settings["PORTAGE_USE"].split())
            settings.setcpv(final)
            self.assertIn("harfbuzz", settings["PORTAGE_USE"].split())
        finally:
            playground.cleanup()
