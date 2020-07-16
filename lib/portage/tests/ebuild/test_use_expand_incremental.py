# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io

from portage import os, _encodings
from portage.dep import Atom
from portage.package.ebuild.config import config
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs

class UseExpandIncrementalTestCase(TestCase):

	def testUseExpandIncremental(self):

		profiles = (
			(
				'base',
				{
					"eapi": ("5",),
					"parent": ("..",),
					"make.defaults": (
						"INPUT_DEVICES=\"keyboard mouse\"",
						"PYTHON_TARGETS=\"python2_7 python3_3\"",
						("USE_EXPAND=\"INPUT_DEVICES PYTHON_TARGETS "
							"VIDEO_CARDS\""),
					)
				}
			),
			(
				'default/linux',
				{
					"eapi": ("5",),
					"make.defaults": (
						"VIDEO_CARDS=\"dummy fbdev v4l\"",
					)
				}
			),
			(
				'default/linux/x86',
				{
					"eapi": ("5",),
					"make.defaults": (
						# Test negative incremental for bug 530222.
						"PYTHON_TARGETS=\"-python3_3\"",
					),
					"parent": ("../../../base",
						"../../../mixins/python/3.4",
						".."
					)
				}
			),
			(
				'mixins/python/3.4',
				{
					"eapi": ("5",),
					"make.defaults": (
						"PYTHON_TARGETS=\"python3_4\"",
					)
				}
			),
		)

		# USE_EXPAND variable settings in make.conf will cause
		# profile settings for the same variable to be discarded
		# (non-incremental behavior). PMS does not govern make.conf
		# behavior.
		user_config = {
			"make.conf" : (
				"VIDEO_CARDS=\"intel\"",
			)
		}

		ebuilds = {
			"x11-base/xorg-drivers-1.15": {
				"EAPI": "5",
				"IUSE": ("input_devices_keyboard input_devices_mouse "
					"videos_cards_dummy video_cards_fbdev "
					"video_cards_v4l video_cards_intel")
			},
			"sys-apps/portage-2.2.14": {
				"EAPI": "5",
				"IUSE": ("python_targets_python2_7 "
					"python_targets_python3_3 python_targets_python3_4")
			},
		}

		package_expected_use = (
			("x11-base/xorg-drivers-1.15", ("input_devices_keyboard",
				"input_devices_mouse", "video_cards_intel",)),
			("sys-apps/portage-2.2.14", ("python_targets_python2_7",
				"python_targets_python3_4"))
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds, user_config=user_config)
		try:
			repo_dir = (playground.settings.repositories.
				get_location_for_name("test_repo"))
			profile_root = os.path.join(repo_dir, "profiles")

			for p, data in profiles:
				prof_path = os.path.join(profile_root, p)
				ensure_dirs(prof_path)
				for k, v in data.items():
					with io.open(os.path.join(prof_path, k), mode="w",
						encoding=_encodings["repo.content"]) as f:
						for line in v:
							f.write("%s\n" % line)

			# The config must be reloaded in order to account
			# for the above profile customizations.
			playground.reload_config()

			depgraph = playground.run(
				["=x11-base/xorg-drivers-1.15"]).depgraph
			settings = config(clone=playground.settings)

			for cpv, expected_use in package_expected_use:
				pkg, existing_node = depgraph._select_package(
					playground.eroot, Atom("=" + cpv))
				settings.setcpv(pkg)
				expected = frozenset(expected_use)
				got = frozenset(settings["PORTAGE_USE"].split())
				self.assertEqual(got, expected,
					"%s != %s" % (got, expected))

		finally:
			playground.cleanup()
