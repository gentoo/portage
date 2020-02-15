# Copyright 2013-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import itertools

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class OrChoicesTestCase(TestCase):

	def testOrChoices(self):
		ebuilds = {
			"dev-lang/vala-0.20.0" : {
				"EAPI": "5",
				"SLOT": "0.20"
			},
			"dev-lang/vala-0.18.0" : {
				"EAPI": "5",
				"SLOT": "0.18"
			},
			#"dev-libs/gobject-introspection-1.36.0" : {
			#	"EAPI": "5",
			#	"RDEPEND" : "!<dev-lang/vala-0.20.0",
			#},
			"dev-libs/gobject-introspection-1.34.0" : {
				"EAPI": "5"
			},
			"sys-apps/systemd-ui-2" : {
				"EAPI": "5",
				"RDEPEND" : "|| ( dev-lang/vala:0.20 dev-lang/vala:0.18 )"
			},
		}

		installed = {
			"dev-lang/vala-0.18.0" : {
				"EAPI": "5",
				"SLOT": "0.18"
			},
			"dev-libs/gobject-introspection-1.34.0" : {
				"EAPI": "5"
			},
			"sys-apps/systemd-ui-2" : {
				"EAPI": "5",
				"RDEPEND" : "|| ( dev-lang/vala:0.20 dev-lang/vala:0.18 )"
			},
		}

		world = ["dev-libs/gobject-introspection", "sys-apps/systemd-ui"]

		test_cases = (
			# Demonstrate that vala:0.20 update is pulled in, for bug #478188
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success=True,
				all_permutations = True,
				mergelist = ['dev-lang/vala-0.20.0']),
			# Verify that vala:0.20 is not pulled in without --deep
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True},
				success=True,
				all_permutations = True,
				mergelist = []),
			# Verify that vala:0.20 is not pulled in without --update
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--selective": True, "--deep": True},
				success=True,
				all_permutations = True,
				mergelist = []),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testInitiallyUnsatisfied(self):

		ebuilds = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/A-2" : {
				"EAPI": "5",
				"SLOT": "0/2"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"RDEPEND": "app-misc/A:="
			},

			"app-misc/C-0" : {
				"EAPI": "5",
				"RDEPEND": "|| ( app-misc/X <app-misc/A-2 )"
			},

		}

		installed = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"RDEPEND": "app-misc/A:0/1="
			},

			"app-misc/C-0" : {
				"EAPI": "5",
				"RDEPEND": "|| ( app-misc/X <app-misc/A-2 )"
			},

		}

		world = ["app-misc/B", "app-misc/C"]

		test_cases = (

			# Test bug #522652, where the unsatisfiable app-misc/X
			# atom is selected, and the dependency is placed into
			# _initially_unsatisfied_deps where it is ignored, causing
			# upgrade to app-misc/A-2 (breaking a dependency of
			# app-misc/C-0).
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				options = {},
				success = True,
				mergelist = ['app-misc/A-1']
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testUseMask(self):

		profile = {
			"use.mask":
			(
				"abi_ppc_32",
			),
		}

		ebuilds = {

			"sys-libs/A-1" : {
				"EAPI": "5",
				"RDEPEND": "|| ( sys-libs/zlib[abi_ppc_32(-)] " + \
					"sys-libs/zlib[abi_x86_32(-)] )"
			},

			"sys-libs/zlib-1.2.8-r1" : {
				"EAPI": "5",
				"IUSE": "abi_ppc_32 abi_x86_32"
			},

			"sys-libs/zlib-1.2.8" : {
				"EAPI": "5",
				"IUSE": ""
			},
		}

		test_cases = (

			# bug #515584: We want to prefer choices that do
			# not require changes to use.mask or use.force.
			# In this case, abi_ppc_32 is use.masked in the
			# profile, so we want to avoid that choice.
			ResolverPlaygroundTestCase(
				["sys-libs/A"],
				options = {},
				success = False,
				use_changes = {
					'sys-libs/zlib-1.2.8-r1': {'abi_x86_32': True}
				},
				mergelist = ["sys-libs/zlib-1.2.8-r1", "sys-libs/A-1"]
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			profile=profile, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.cleanup()

	def testConflictMissedUpdate(self):

		ebuilds = {
			"dev-lang/ocaml-4.02.1" : {
				"EAPI": "5",
				"SLOT": "0/4.02.1",
			},

			"dev-lang/ocaml-4.01.0" : {
				"EAPI": "5",
				"SLOT": "0/4.01.0",
			},

			"dev-ml/lablgl-1.05" : {
				"EAPI": "5",
				"DEPEND": (">=dev-lang/ocaml-3.10.2:= "
					"|| ( dev-ml/labltk:= <dev-lang/ocaml-4.02 )"),
				"RDEPEND": (">=dev-lang/ocaml-3.10.2:= "
					"|| ( dev-ml/labltk:= <dev-lang/ocaml-4.02 )"),
			},

			"dev-ml/labltk-8.06.0" : {
				"EAPI": "5",
				"SLOT": "0/8.06.0",
				"DEPEND": ">=dev-lang/ocaml-4.02:=",
				"RDEPEND": ">=dev-lang/ocaml-4.02:=",
			},
		}

		installed = {
			"dev-lang/ocaml-4.01.0" : {
				"EAPI": "5",
				"SLOT": "0/4.01.0",
			},

			"dev-ml/lablgl-1.05" : {
				"EAPI": "5",
				"DEPEND": (">=dev-lang/ocaml-3.10.2:0/4.01.0= "
					"|| ( dev-ml/labltk:= <dev-lang/ocaml-4.02 )"),
				"RDEPEND": (">=dev-lang/ocaml-3.10.2:0/4.01.0= "
					"|| ( dev-ml/labltk:= <dev-lang/ocaml-4.02 )"),
			},
		}

		world = (
			"dev-lang/ocaml",
			"dev-ml/lablgl",
		)

		test_cases = (

			# bug #531656: If an ocaml update is desirable,
			# then we need to pull in dev-ml/labltk.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = [
					"dev-lang/ocaml-4.02.1",
					"dev-ml/labltk-8.06.0",
					"dev-ml/lablgl-1.05",
				]
			),

		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds, installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			# Disable debug so that cleanup works.
			playground.debug = False
			playground.cleanup()

	def test_python_slot(self):
		ebuilds = {

			"dev-lang/python-3.8" : {
				"EAPI": "7",
				"SLOT": "3.8"
			},

			"dev-lang/python-3.7" : {
				"EAPI": "7",
				"SLOT": "3.7"
			},

			"dev-lang/python-3.6" : {
				"EAPI": "7",
				"SLOT": "3.6"
			},

			"app-misc/bar-1" : {
				"EAPI": "7",
				"IUSE": "python_targets_python3_6 +python_targets_python3_7",
				"RDEPEND": "python_targets_python3_7? ( dev-lang/python:3.7 ) python_targets_python3_6? ( dev-lang/python:3.6 )"
			},

			"app-misc/foo-1" : {
				"EAPI": "7",
				"RDEPEND": "|| ( dev-lang/python:3.8 dev-lang/python:3.7 dev-lang/python:3.6 )"
			},

		}

		installed = {

			"dev-lang/python-3.7" : {
				"EAPI": "7",
				"SLOT": "3.7"
			},

			"app-misc/bar-1" : {
				"EAPI": "7",
				"IUSE": "python_targets_python3_6 +python_targets_python3_7",
				"USE": "python_targets_python3_7",
				"RDEPEND": "dev-lang/python:3.7"
			},

			"app-misc/foo-1" : {
				"EAPI": "7",
				"RDEPEND": "|| ( dev-lang/python:3.8 dev-lang/python:3.7 dev-lang/python:3.6 )"
			},

		}

		world = ["app-misc/foo", "app-misc/bar"]

		test_cases = (

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ['dev-lang/python-3.8']
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

		installed = {

			"dev-lang/python-3.8" : {
				"EAPI": "7",
				"SLOT": "3.8"
			},

			"dev-lang/python-3.7" : {
				"EAPI": "7",
				"SLOT": "3.7"
			},

			"app-misc/bar-1" : {
				"EAPI": "7",
				"IUSE": "python_targets_python3_6 +python_targets_python3_7",
				"USE": "python_targets_python3_7",
				"RDEPEND": "dev-lang/python:3.7"
			},

			"app-misc/foo-1" : {
				"EAPI": "7",
				"RDEPEND": "|| ( dev-lang/python:3.8 dev-lang/python:3.7 dev-lang/python:3.6 )"
			},

		}

		test_cases = (
			# Test for bug 707108, where a new python slot was erroneously
			# removed by emerge --depclean.
			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True},
				success=True,
				cleanlist=[],
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

	def test_virtual_w3m(self):
		ebuilds = {

			'app-text/xmlto-0.0.28-r1' : {
				'EAPI': '7',
				'RDEPEND': '|| ( virtual/w3m www-client/lynx www-client/elinks )'
			},

			'www-client/elinks-0.13_pre_pre20180225' : {
				'EAPI': '7',
			},

			'www-client/lynx-2.9.0_pre4' : {
				'EAPI': '7',
			},

			'virtual/w3m-0' : {
				'EAPI': '7',
				'RDEPEND': '|| ( www-client/w3m www-client/w3mmee )'
			},

			'www-client/w3m-0.5.3_p20190105' : {
				'EAPI': '7',
			},

			'www-client/w3mmee-0.3.2_p24-r10' : {
				'EAPI': '7',
			},

		}

		installed = {

			'app-text/xmlto-0.0.28-r1' : {
				'EAPI': '7',
				'RDEPEND': '|| ( virtual/w3m www-client/lynx www-client/elinks )'
			},

			'www-client/elinks-0.13_pre_pre20180225' : {
				'EAPI': '7',
			},

			'www-client/lynx-2.9.0_pre4' : {
				'EAPI': '7',
			},

		}

		world = ['app-text/xmlto', 'www-client/elinks', 'www-client/lynx']

		test_cases = (

			# Test for bug 649622 (without www-client/w3m installed),
			# where virtual/w3m was pulled in only to be removed by the
			# next emerge --depclean.
			ResolverPlaygroundTestCase(
				['@world'],
				options = {'--update': True, '--deep': True},
				success = True,
				mergelist = []
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

		installed = dict(itertools.chain(installed.items(), {

			'www-client/w3m-0.5.3_p20190105' : {
				'EAPI': '7',
			},

		}.items()))

		test_cases = (

			# Test for bug 649622 (with www-client/w3m installed),
			# where virtual/w3m was pulled in only to be removed by the
			# next emerge --depclean.
			ResolverPlaygroundTestCase(
				['@world'],
				options = {'--update': True, '--deep': True},
				success = True,
				mergelist = []
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

		installed = dict(itertools.chain(installed.items(), {

			'virtual/w3m-0' : {
				'EAPI': '7',
				'RDEPEND': '|| ( www-client/w3m www-client/w3mmee )'
			},

		}.items()))

		test_cases = (

			# Test for bug 649622, where virtual/w3m is removed by
			# emerge --depclean immediately after it's installed
			# by a world update. Note that removal of virtual/w3m here
			# is essentially indistinguishable from removal of
			# dev-util/cmake-bootstrap in the depclean test case for
			# bug 703440.
			ResolverPlaygroundTestCase(
				[],
				options={'--depclean': True},
				success=True,
				cleanlist=['virtual/w3m-0', 'www-client/w3m-0.5.3_p20190105'],
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()


		test_cases = (

			# Test for behavior reported in bug 649622 comment #10, where
			# depclean removed virtual/w3m-0 even though www-client/w3m
			# was in the world file. Since nothing is removed here, it
			# means that we have not reproduced the behavior reported in
			# this comment.
			ResolverPlaygroundTestCase(
				[],
				options={'--depclean': True},
				success=True,
				cleanlist=[],
			),

		)

		world += ['www-client/w3m']

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()


	def test_virtual_w3m_realistic(self):
		"""
		Test for bug 649622 with realistic www-client/w3m dependencies copied
		from real ebuilds.
		"""
		ebuilds = {

			'app-misc/neofetch-6.1.0': {
				'EAPI': '7',
				'RDEPEND': 'www-client/w3m'
			},

			'app-text/xmlto-0.0.28-r1' : {
				'EAPI': '7',
				'RDEPEND': '|| ( virtual/w3m www-client/lynx www-client/elinks )'
			},

			'mail-client/neomutt-20191207': {
				'EAPI': '7',
				'RDEPEND': '|| ( www-client/lynx www-client/w3m www-client/elinks )'
			},

			'www-client/elinks-0.13_pre_pre20180225' : {
				'EAPI': '7',
			},

			'www-client/lynx-2.9.0_pre4' : {
				'EAPI': '7',
			},

			'virtual/w3m-0' : {
				'EAPI': '7',
				'RDEPEND': '|| ( www-client/w3m www-client/w3mmee )'
			},

			'www-client/w3m-0.5.3_p20190105' : {
				'EAPI': '7',
			},

			'www-client/w3mmee-0.3.2_p24-r10' : {
				'EAPI': '7',
			},

			'x11-base/xorg-server-1.20.7' : {
				'EAPI': '7',
				'RDEPEND': '|| ( www-client/links www-client/lynx www-client/w3m ) app-text/xmlto',
			}
		}

		installed = {

			'app-misc/neofetch-6.1.0': {
				'EAPI': '7',
				'RDEPEND': 'www-client/w3m'
			},

			'app-text/xmlto-0.0.28-r1' : {
				'EAPI': '7',
				'RDEPEND': '|| ( virtual/w3m www-client/lynx www-client/elinks )'
			},

			'mail-client/neomutt-20191207': {
				'EAPI': '7',
				'RDEPEND': '|| ( www-client/lynx www-client/w3m www-client/elinks )'
			},

			'www-client/lynx-2.9.0_pre4' : {
				'EAPI': '7',
			},

			'www-client/w3m-0.5.3_p20190105' : {
				'EAPI': '7',
			},

			'x11-base/xorg-server-1.20.7' : {
				'EAPI': '7',
				'RDEPEND': '|| ( www-client/links www-client/lynx www-client/w3m ) app-text/xmlto',
			}
		}

		world = ['app-misc/neofetch', 'mail-client/neomutt', 'www-client/lynx', 'x11-base/xorg-server']

		test_cases = (

			# Test for bug 649622 (with www-client/w3m installed via
			# xorg-server dependency), where virtual/w3m was pulled in
			# only to be removed by the next emerge --depclean. Note
			# that graph_order must be deterministic in order to achieve
			# deterministic results which are consistent between both
			# update and removal (depclean) actions.
			ResolverPlaygroundTestCase(
				['@world'],
				options = {'--update': True, '--deep': True},
				success = True,
				mergelist=['virtual/w3m-0'],
				graph_order=['@world', '@profile', '@selected', '@system', '[nomerge]app-misc/neofetch-6.1.0', '[nomerge]mail-client/neomutt-20191207', '[nomerge]www-client/lynx-2.9.0_pre4', '[nomerge]x11-base/xorg-server-1.20.7', '[nomerge]app-text/xmlto-0.0.28-r1', '[nomerge]www-client/w3m-0.5.3_p20190105', 'virtual/w3m-0'],
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()


		installed = dict(itertools.chain(installed.items(), {

			'virtual/w3m-0' : {
				'EAPI': '7',
				'RDEPEND': '|| ( www-client/w3m www-client/w3mmee )'
			},

		}.items()))

		test_cases = (

			# Test for bug 649622, where virtual/w3m is removed by
			# emerge --depclean immediately after it's installed
			# by a world update. Since virtual/w3m-0 is not removed
			# here, this case fails to reproduce bug 649622. Note
			# that graph_order must be deterministic in order to achieve
			# deterministic results which are consistent between both
			# update and removal (depclean) actions.
			ResolverPlaygroundTestCase(
				[],
				options={'--depclean': True},
				success=True,
				cleanlist=[],
				graph_order=['@world', '@____depclean_protected_set____', '@profile', '@selected', '@system', '[nomerge]app-misc/neofetch-6.1.0', '[nomerge]mail-client/neomutt-20191207', '[nomerge]www-client/lynx-2.9.0_pre4', '[nomerge]x11-base/xorg-server-1.20.7', '[nomerge]app-text/xmlto-0.0.28-r1', '[nomerge]www-client/w3m-0.5.3_p20190105', '[nomerge]virtual/w3m-0'],
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()


class OrChoicesLibpostprocTestCase(TestCase):

	def testOrChoicesLibpostproc(self):
		# This test case is expected to fail after the fix for bug 706278,
		# since the "undesirable" slot upgrade which triggers a blocker conflict
		# in this test case is practically indistinguishable from a desirable
		# slot upgrade. This particular blocker conflict is no longer relevant,
		# since current versions of media-libs/libpostproc are no longer
		# compatible with any available media-video/ffmpeg slot. In order to
		# solve this test case, some fancy backtracking (like for bug 382421)
		# will be required.
		self.todo = True

		ebuilds = {
			"media-video/ffmpeg-0.10" : {
				"EAPI": "5",
				"SLOT": "0.10"
			},
			"media-video/ffmpeg-1.2.2" : {
				"EAPI": "5",
				"SLOT": "0"
			},
			"media-libs/libpostproc-0.8.0.20121125" : {
				"EAPI": "5"
			},
			"media-plugins/gst-plugins-ffmpeg-0.10.13_p201211-r1" : {
				"EAPI": "5",
				"RDEPEND" : "|| ( media-video/ffmpeg:0 media-libs/libpostproc )"
			},
		}

		installed = {
			"media-video/ffmpeg-0.10" : {
				"EAPI": "5",
				"SLOT": "0.10"
			},
			"media-libs/libpostproc-0.8.0.20121125" : {
				"EAPI": "5"
			},
			"media-plugins/gst-plugins-ffmpeg-0.10.13_p201211-r1" : {
				"EAPI": "5",
				"RDEPEND" : "|| ( media-video/ffmpeg:0 media-libs/libpostproc )"
			},
		}

		world = ["media-plugins/gst-plugins-ffmpeg"]

		test_cases = (
			# Demonstrate that libpostproc is preferred
			# over ffmpeg:0 for bug #480736.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success=True,
				all_permutations = True,
				mergelist = []),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed,
			world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
