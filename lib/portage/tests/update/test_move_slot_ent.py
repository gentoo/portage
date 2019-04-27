# Copyright 2012-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import textwrap

import portage
from portage import os
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs
from portage._global_updates import _do_global_updates

class MoveSlotEntTestCase(TestCase):

	def testMoveSlotEnt(self):

		ebuilds = {

			"dev-libs/A-2::dont_apply_updates" : {
				"EAPI": "5",
				"SLOT": "0/2.30",
			},

			"dev-libs/B-2::dont_apply_updates" : {
				"SLOT": "0",
			},

			"dev-libs/C-2.1::dont_apply_updates" : {
				"EAPI": "5",
				"SLOT": "0/2.1",
			},

		}

		installed = {

			"dev-libs/A-1::test_repo" : {
				"EAPI": "5",
				"SLOT": "0/2.30",
			},

			"dev-libs/B-1::test_repo" : {
				"SLOT": "0",
			},

			"dev-libs/C-1::test_repo" : {
				"EAPI": "5",
				"SLOT": "0/1",
			},

		}

		binpkgs = {

			"dev-libs/A-1::test_repo" : {
				"EAPI": "5",
				"SLOT": "0/2.30",
			},

			"dev-libs/A-2::dont_apply_updates" : {
				"EAPI": "5",
				"SLOT": "0/2.30",
			},

			"dev-libs/B-1::test_repo" : {
				"SLOT": "0",
			},

			"dev-libs/B-2::dont_apply_updates" : {
				"SLOT": "0",
			},

			"dev-libs/C-1::test_repo" : {
				"EAPI": "5",
				"SLOT": "0/1",
			},

			"dev-libs/C-2.1::dont_apply_updates" : {
				"EAPI": "5",
				"SLOT": "0/2.1",
			},

		}

		updates = textwrap.dedent("""
			slotmove dev-libs/A 0 2
			slotmove dev-libs/B 0 1
			slotmove dev-libs/C 0 1
		""")

		playground = ResolverPlayground(binpkgs=binpkgs,
			ebuilds=ebuilds, installed=installed)

		settings = playground.settings
		trees = playground.trees
		eroot = settings["EROOT"]
		test_repo_location = settings.repositories["test_repo"].location
		portdb = trees[eroot]["porttree"].dbapi
		vardb = trees[eroot]["vartree"].dbapi
		bindb = trees[eroot]["bintree"].dbapi

		updates_dir = os.path.join(test_repo_location, "profiles", "updates")

		try:
			ensure_dirs(updates_dir)
			with open(os.path.join(updates_dir, "1Q-2010"), 'w') as f:
				f.write(updates)

			# Create an empty updates directory, so that this
			# repo doesn't inherit updates from the main repo.
			ensure_dirs(os.path.join(
				portdb.getRepositoryPath("dont_apply_updates"),
				"profiles", "updates"))

			global_noiselimit = portage.util.noiselimit
			portage.util.noiselimit = -2
			try:
				_do_global_updates(trees, {})
			finally:
				portage.util.noiselimit = global_noiselimit

			# Workaround for cache validation not working
			# correctly when filesystem has timestamp precision
			# of 1 second.
			vardb._clear_cache()

			# 0/2.30 -> 2/2.30
			self.assertEqual("2/2.30",
				vardb.aux_get("dev-libs/A-1", ["SLOT"])[0])
			self.assertEqual("2/2.30",
				bindb.aux_get("dev-libs/A-1", ["SLOT"])[0])

			# 0 -> 1
			self.assertEqual("1",
				vardb.aux_get("dev-libs/B-1", ["SLOT"])[0])
			self.assertEqual("1",
				bindb.aux_get("dev-libs/B-1", ["SLOT"])[0])

			# 0/1 -> 1 (equivalent to 1/1)
			self.assertEqual("1",
				vardb.aux_get("dev-libs/C-1", ["SLOT"])[0])
			self.assertEqual("1",
				bindb.aux_get("dev-libs/C-1", ["SLOT"])[0])

			# dont_apply_updates
			self.assertEqual("0/2.30",
				bindb.aux_get("dev-libs/A-2", ["SLOT"])[0])
			self.assertEqual("0",
				bindb.aux_get("dev-libs/B-2", ["SLOT"])[0])
			self.assertEqual("0/2.1",
				bindb.aux_get("dev-libs/C-2.1", ["SLOT"])[0])

		finally:
			playground.cleanup()
