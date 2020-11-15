# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotOperatorBdependTestCase(TestCase):

	def testSlotOperatorBdepend(self):
		"""
		Test regular dev-lang/go upgrade, with rebuild of packages
		that have dev-lang/go:= in BDEPEND.
		"""

		ebuilds = {
			"app-emulation/buildah-1.16.1":{
				"EAPI": "7",
				"BDEPEND": "dev-lang/go:=",
			},

			"app-emulation/libpod-2.1.0":{
				"EAPI": "7",
				"BDEPEND": "dev-lang/go:=",
			},

			"dev-lang/go-1.15.5":{
				"EAPI": "7",
				"SLOT": "0/1.15.5"
			},

			"dev-lang/go-1.14.12" : {
				"EAPI": "7",
				"SLOT": "0/1.14.12"
			},
		}

		binpkgs = {
			"app-emulation/buildah-1.16.1":{
				"EAPI": "7",
				"BDEPEND": "dev-lang/go:0/1.14.12=",
			},
			"app-emulation/libpod-2.1.0":{
				"EAPI": "7",
				"BDEPEND": "dev-lang/go:0/1.14.12=",
			},
			"dev-lang/go-1.14.12" : {
				"EAPI": "7",
				"SLOT": "0/1.14.12"
			},
		}

		installed = {
			"app-emulation/buildah-1.16.1":{
				"EAPI": "7",
				"BDEPEND": "dev-lang/go:0/1.14.12=",
			},
			"app-emulation/libpod-2.1.0":{
				"EAPI": "7",
				"BDEPEND": "dev-lang/go:0/1.14.12=",
			},
			"dev-lang/go-1.14.12" : {
				"EAPI": "7",
				"SLOT": "0/1.14.12"
			},
		}

		world = ["app-emulation/buildah", "app-emulation/libpod"]

		test_cases = (

			# Test rebuild triggered by slot operator := dependency in BDEPEND.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--update": True,
					"--deep": True,
				},
				success = True,
				mergelist = ["dev-lang/go-1.15.5", "app-emulation/buildah-1.16.1", "app-emulation/libpod-2.1.0"]
			),

			# Test the above case with --usepkg --with-bdeps=y. It should not use the
			# binary packages because rebuild is needed.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--usepkg": True,
					"--with-bdeps": "y",
					"--update": True,
					"--deep": True,
				},
				success = True,
				mergelist = ["dev-lang/go-1.15.5", "app-emulation/buildah-1.16.1", "app-emulation/libpod-2.1.0"]
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, binpkgs=binpkgs,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

	def testSlotOperatorBdependAfterBreakage(self):
		"""
		Test rebuild of packages that have dev-lang/go:= in BDEPEND,
		after the built slot operator deps have already been broken
		by an earlier dev-lang/go upgrade.
		"""

		ebuilds = {
			"app-emulation/buildah-1.16.1":{
				"EAPI": "7",
				"BDEPEND": "dev-lang/go:=",
			},

			"app-emulation/libpod-2.1.0":{
				"EAPI": "7",
				"BDEPEND": "dev-lang/go:=",
			},

			"dev-lang/go-1.15.5":{
				"EAPI": "7",
				"SLOT": "0/1.15.5"
			},

			"dev-lang/go-1.14.12" : {
				"EAPI": "7",
				"SLOT": "0/1.14.12"
			},
		}

		binpkgs = {
			"app-emulation/buildah-1.16.1":{
				"EAPI": "7",
				"BDEPEND": "dev-lang/go:0/1.14.12=",
			},
			"app-emulation/libpod-2.1.0":{
				"EAPI": "7",
				"BDEPEND": "dev-lang/go:0/1.14.12=",
			},
			"dev-lang/go-1.14.12" : {
				"EAPI": "7",
				"SLOT": "0/1.14.12"
			},
			"dev-lang/go-1.15.5" : {
				"EAPI": "7",
				"SLOT": "0/1.15.5"
			},
		}

		installed = {
			"app-emulation/buildah-1.16.1":{
				"EAPI": "7",
				"BDEPEND": "dev-lang/go:0/1.14.12=",
			},
			"app-emulation/libpod-2.1.0":{
				"EAPI": "7",
				"BDEPEND": "dev-lang/go:0/1.14.12=",
			},
			"dev-lang/go-1.15.5" : {
				"EAPI": "7",
				"SLOT": "0/1.15.5"
			},
		}

		world = ["app-emulation/buildah", "app-emulation/libpod"]

		test_cases = (

			# Test rebuild triggered by slot operator := dependency in BDEPEND.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--update": True,
					"--deep": True,
				},
				success = True,
				mergelist = ["app-emulation/buildah-1.16.1", "app-emulation/libpod-2.1.0"]
			),

			# Test the above case with --usepkg --with-bdeps=y. It should not use the
			# binary packages because rebuild is needed.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--usepkg": True,
					"--with-bdeps": "y",
					"--update": True,
					"--deep": True,
				},
				success = True,
				mergelist = ["app-emulation/buildah-1.16.1", "app-emulation/libpod-2.1.0"]
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, binpkgs=binpkgs,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
