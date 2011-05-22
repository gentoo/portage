# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class MergeOrderTestCase(TestCase):

	def testMergeOrder(self):
		ebuilds = {
			"app-misc/blocker-buildtime-a-1" : {},
			"app-misc/blocker-buildtime-unbuilt-a-1" : {
				"DEPEND" : "!app-misc/installed-blocker-a",
			},
			"app-misc/blocker-buildtime-unbuilt-hard-a-1" : {
				"EAPI"   : "2",
				"DEPEND" : "!!app-misc/installed-blocker-a",
			},
			"app-misc/blocker-update-order-a-1" : {},
			"app-misc/blocker-update-order-hard-a-1" : {},
			"app-misc/blocker-update-order-hard-unsolvable-a-1" : {},
			"app-misc/blocker-runtime-a-1" : {},
			"app-misc/blocker-runtime-b-1" : {},
			"app-misc/blocker-runtime-hard-a-1" : {},
			"app-misc/circ-buildtime-a-0": {},
			"app-misc/circ-buildtime-a-1": {
				"RDEPEND": "app-misc/circ-buildtime-b",
			},
			"app-misc/circ-buildtime-b-1": {
				"RDEPEND": "app-misc/circ-buildtime-c",
			},
			"app-misc/circ-buildtime-c-1": {
				"DEPEND": "app-misc/circ-buildtime-a",
			},
			"app-misc/circ-buildtime-unsolvable-a-1": {
				"RDEPEND": "app-misc/circ-buildtime-unsolvable-b",
			},
			"app-misc/circ-buildtime-unsolvable-b-1": {
				"RDEPEND": "app-misc/circ-buildtime-unsolvable-c",
			},
			"app-misc/circ-buildtime-unsolvable-c-1": {
				"DEPEND": "app-misc/circ-buildtime-unsolvable-a",
			},
			"app-misc/circ-post-runtime-a-1": {
				"PDEPEND": "app-misc/circ-post-runtime-b",
			},
			"app-misc/circ-post-runtime-b-1": {
				"RDEPEND": "app-misc/circ-post-runtime-c",
			},
			"app-misc/circ-post-runtime-c-1": {
				"RDEPEND": "app-misc/circ-post-runtime-a",
			},
			"app-misc/circ-runtime-a-1": {
				"RDEPEND": "app-misc/circ-runtime-b",
			},
			"app-misc/circ-runtime-b-1": {
				"RDEPEND": "app-misc/circ-runtime-c",
			},
			"app-misc/circ-runtime-c-1": {
				"RDEPEND": "app-misc/circ-runtime-a",
			},
			"app-misc/circ-satisfied-a-0": {
				"RDEPEND": "app-misc/circ-satisfied-b",
			},
			"app-misc/circ-satisfied-a-1": {
				"RDEPEND": "app-misc/circ-satisfied-b",
			},
			"app-misc/circ-satisfied-b-0": {
				"RDEPEND": "app-misc/circ-satisfied-c",
			},
			"app-misc/circ-satisfied-b-1": {
				"RDEPEND": "app-misc/circ-satisfied-c",
			},
			"app-misc/circ-satisfied-c-0": {
				"DEPEND": "app-misc/circ-satisfied-a",
				"RDEPEND": "app-misc/circ-satisfied-a",
			},
			"app-misc/circ-satisfied-c-1": {
				"DEPEND": "app-misc/circ-satisfied-a",
				"RDEPEND": "app-misc/circ-satisfied-a",
			},
			"app-misc/installed-blocker-a-1" : {
				"EAPI"   : "2",
				"DEPEND" : "!app-misc/blocker-buildtime-a",
				"RDEPEND" : "!app-misc/blocker-runtime-a !app-misc/blocker-runtime-b !!app-misc/blocker-runtime-hard-a",
			},
			"app-misc/installed-old-version-blocks-a-1" : {
				"RDEPEND" : "!app-misc/blocker-update-order-a",
			},
			"app-misc/installed-old-version-blocks-a-2" : {},
			"app-misc/installed-old-version-blocks-hard-a-1" : {
				"EAPI"    : "2",
				"RDEPEND" : "!!app-misc/blocker-update-order-hard-a",
			},
			"app-misc/installed-old-version-blocks-hard-a-2" : {},
			"app-misc/installed-old-version-blocks-hard-unsolvable-a-1" : {
				"EAPI"    : "2",
				"RDEPEND" : "!!app-misc/blocker-update-order-hard-unsolvable-a",
			},
			"app-misc/installed-old-version-blocks-hard-unsolvable-a-2" : {
				"DEPEND"  : "app-misc/blocker-update-order-hard-unsolvable-a",
				"RDEPEND" : "",
			},
			"app-misc/some-app-a-1": {
				"RDEPEND": "app-misc/circ-runtime-a app-misc/circ-runtime-b",
			},
			"app-misc/some-app-b-1": {
				"RDEPEND": "app-misc/circ-post-runtime-a app-misc/circ-post-runtime-b",
			},
			"app-misc/some-app-c-1": {
				"RDEPEND": "app-misc/circ-buildtime-a app-misc/circ-buildtime-b",
			},
			"sys-apps/portage-2.1.9.42" : {
				"DEPEND"  : "dev-lang/python",
				"RDEPEND" : "dev-lang/python",
			},
			"sys-apps/portage-2.1.9.49" : {
				"DEPEND"  : "dev-lang/python",
				"RDEPEND" : "dev-lang/python",
			},
			"dev-lang/python-3.1" : {},
			"dev-lang/python-3.2" : {},
		}

		installed = {
			"app-misc/circ-buildtime-a-0": {},
			"app-misc/circ-satisfied-a-0": {
				"RDEPEND": "app-misc/circ-satisfied-b",
			},
			"app-misc/circ-satisfied-b-0": {
				"RDEPEND": "app-misc/circ-satisfied-c",
			},
			"app-misc/circ-satisfied-c-0": {
				"DEPEND": "app-misc/circ-satisfied-a",
				"RDEPEND": "app-misc/circ-satisfied-a",
			},
			"app-misc/installed-blocker-a-1" : {
				"EAPI"   : "2",
				"DEPEND" : "!app-misc/blocker-buildtime-a",
				"RDEPEND" : "!app-misc/blocker-runtime-a !app-misc/blocker-runtime-b !!app-misc/blocker-runtime-hard-a",
			},
			"app-misc/installed-old-version-blocks-a-1" : {
				"RDEPEND" : "!app-misc/blocker-update-order-a",
			},
			"app-misc/installed-old-version-blocks-hard-a-1" : {
				"EAPI"    : "2",
				"RDEPEND" : "!!app-misc/blocker-update-order-hard-a",
			},
			"app-misc/installed-old-version-blocks-hard-unsolvable-a-1" : {
				"EAPI"    : "2",
				"RDEPEND" : "!!app-misc/blocker-update-order-hard-unsolvable-a",
			},
			"sys-apps/portage-2.1.9.42" : {
				"DEPEND"  : "dev-lang/python",
				"RDEPEND" : "dev-lang/python",
			},
			"dev-lang/python-3.1" : {},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["app-misc/some-app-a"],
				success = True,
				ambiguous_merge_order = True,
				mergelist = [("app-misc/circ-runtime-a-1", "app-misc/circ-runtime-b-1", "app-misc/circ-runtime-c-1"), "app-misc/some-app-a-1"]),
			ResolverPlaygroundTestCase(
				["app-misc/some-app-a"],
				success = True,
				ambiguous_merge_order = True,
				mergelist = [("app-misc/circ-runtime-c-1", "app-misc/circ-runtime-b-1", "app-misc/circ-runtime-a-1"), "app-misc/some-app-a-1"]),
			# Test unsolvable circular dep that is RDEPEND in one
			# direction and DEPEND in the other.
			ResolverPlaygroundTestCase(
				["app-misc/circ-buildtime-unsolvable-a"],
				success = False,
				circular_dependency_solutions = {}),
			# Test optimal merge order for a circular dep that is
			# RDEPEND in one direction and DEPEND in the other.
			# This requires an installed instance of the DEPEND
			# package in order to be solvable.
			ResolverPlaygroundTestCase(
				["app-misc/some-app-c", "app-misc/circ-buildtime-a"],
				success = True,
				ambiguous_merge_order = True,
				mergelist = [("app-misc/circ-buildtime-b-1", "app-misc/circ-buildtime-c-1"), "app-misc/circ-buildtime-a-1", "app-misc/some-app-c-1"]),
			# Test optimal merge order for a circular dep that is
			# RDEPEND in one direction and PDEPEND in the other.
			ResolverPlaygroundTestCase(
				["app-misc/some-app-b"],
				success = True,
				ambiguous_merge_order = True,
				mergelist = ["app-misc/circ-post-runtime-a-1", ("app-misc/circ-post-runtime-b-1", "app-misc/circ-post-runtime-c-1"), "app-misc/some-app-b-1"]),
			# Test optimal merge order for a circular dep that is
			# RDEPEND in one direction and DEPEND in the other,
			# with all dependencies initially satisfied. Optimally,
			# the DEPEND/buildtime dep should be updated before the
			# package that depends on it, even though it's feasible
			# to update it later since it is already satisfied.
			ResolverPlaygroundTestCase(
				["app-misc/circ-satisfied-a", "app-misc/circ-satisfied-b", "app-misc/circ-satisfied-c"],
				success = True,
				all_permutations = True,
				ambiguous_merge_order = True,
				merge_order_assertions = (("app-misc/circ-satisfied-a-1", "app-misc/circ-satisfied-c-1"),),
				mergelist = [("app-misc/circ-satisfied-a-1", "app-misc/circ-satisfied-b-1", "app-misc/circ-satisfied-c-1")]),
			# installed package has buildtime-only blocker
			# that should be ignored
			ResolverPlaygroundTestCase(
				["app-misc/blocker-buildtime-a"],
				success = True,
				mergelist = ["app-misc/blocker-buildtime-a-1"]),
			# We're installing a package that an old version of
			# an installed package blocks. However, an update is
			# available to the old package. The old package should
			# be updated first, in order to solve the blocker without
			# any need for blocking packages to temporarily overlap.
			ResolverPlaygroundTestCase(
				["app-misc/blocker-update-order-a", "app-misc/installed-old-version-blocks-a"],
				success = True,
				all_permutations = True,
				mergelist = ["app-misc/installed-old-version-blocks-a-2", "app-misc/blocker-update-order-a-1"]),
			# This is the same as above but with a hard blocker. The hard
			# blocker is solved automatically since the update makes it
			# irrelevant.
			ResolverPlaygroundTestCase(
				["app-misc/blocker-update-order-hard-a", "app-misc/installed-old-version-blocks-hard-a"],
				success = True,
				all_permutations = True,
				mergelist = ["app-misc/installed-old-version-blocks-hard-a-2", "app-misc/blocker-update-order-hard-a-1"]),
			# This is similar to the above case except that it's unsolvable
			# due to merge order, unless bug 250286 is implemented so that
			# the installed blocker will be unmerged before installation
			# of the package it blocks (rather than after like a soft blocker
			# would be handled). The "unmerge before" behavior requested
			# in bug 250286 must be optional since essential programs or
			# libraries may be temporarily unavailable during a
			# non-overlapping update like this.
			ResolverPlaygroundTestCase(
				["app-misc/blocker-update-order-hard-unsolvable-a", "app-misc/installed-old-version-blocks-hard-unsolvable-a"],
				success = False,
				all_permutations = True,
				ambiguous_merge_order = True,
				merge_order_assertions = (('app-misc/blocker-update-order-hard-unsolvable-a-1', 'app-misc/installed-old-version-blocks-hard-unsolvable-a-2'),),
				mergelist = [('app-misc/blocker-update-order-hard-unsolvable-a-1', 'app-misc/installed-old-version-blocks-hard-unsolvable-a-2', '!!app-misc/blocker-update-order-hard-unsolvable-a')]),
			# The installed package has runtime blockers that
			# should cause it to be uninstalled. The uninstall
			# task is executed only after blocking packages have
			# been merged.
			# TODO: distinguish between install/uninstall tasks in mergelist
			ResolverPlaygroundTestCase(
				["app-misc/blocker-runtime-a", "app-misc/blocker-runtime-b"],
				success = True,
				all_permutations = True,
				ambiguous_merge_order = True,
				mergelist = [("app-misc/blocker-runtime-a-1", "app-misc/blocker-runtime-b-1"), "app-misc/installed-blocker-a-1", ("!app-misc/blocker-runtime-a", "!app-misc/blocker-runtime-b")]),
			# We have a soft buildtime blocker against an installed
			# package that should cause it to be uninstalled. Note that with
			# soft blockers, the blocking packages are allowed to temporarily
			# overlap. This allows any essential programs/libraries provided
			# by both packages to be available at all times.
			# TODO: distinguish between install/uninstall tasks in mergelist
			ResolverPlaygroundTestCase(
				["app-misc/blocker-buildtime-unbuilt-a"],
				success = True,
				mergelist = ["app-misc/blocker-buildtime-unbuilt-a-1", "app-misc/installed-blocker-a-1", "!app-misc/installed-blocker-a"]),
			# We have a hard buildtime blocker against an installed
			# package that will not resolve automatically (unless
			# the option requested in bug 250286 is implemented).
			ResolverPlaygroundTestCase(
				["app-misc/blocker-buildtime-unbuilt-hard-a"],
				success = False,
				mergelist = ['app-misc/blocker-buildtime-unbuilt-hard-a-1', '!!app-misc/installed-blocker-a']),
			# An installed package has a hard runtime blocker that
			# will not resolve automatically (unless the option
			# requested in bug 250286 is implemented).
			ResolverPlaygroundTestCase(
				["app-misc/blocker-runtime-hard-a"],
				success = False,
				mergelist = ['app-misc/blocker-runtime-hard-a-1', '!!app-misc/blocker-runtime-hard-a']),
			# Test that PORTAGE_PACKAGE_ATOM is merged asap.
			ResolverPlaygroundTestCase(
				["dev-lang/python", portage.const.PORTAGE_PACKAGE_ATOM],
				success = True,
				all_permutations = True,
				mergelist = ['sys-apps/portage-2.1.9.49', 'dev-lang/python-3.2']),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
