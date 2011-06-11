# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import shutil
import tempfile

from portage.dbapi.virtual import fakedbapi
from portage.package.ebuild.config import config
from portage.tests import TestCase

class TestFakedbapi(TestCase):

	def testFakedbapi(self):
		packages = (
			("sys-apps/portage-2.1.10", {
				"EAPI"         : "2",
				"IUSE"         : "ipc doc",
				"repository"   : "gentoo",
				"SLOT"         : "0",
				"USE"          : "ipc",
			}),
			("virtual/package-manager-0", {
				"EAPI"         : "0",
				"repository"   : "gentoo",
				"SLOT"         : "0",
			}),
		)

		match_tests = (
			("sys-apps/portage:0[ipc]",             ["sys-apps/portage-2.1.10"]),
			("sys-apps/portage:0[-ipc]",            []),
			("sys-apps/portage:0[doc]",             []),
			("sys-apps/portage:0[-doc]",            ["sys-apps/portage-2.1.10"]),
			("sys-apps/portage:0::gentoo[ipc]",     ["sys-apps/portage-2.1.10"]),
			("sys-apps/portage:0::multilib[ipc]",   []),
			("virtual/package-manager",             ["virtual/package-manager-0"]),
		)

		tempdir = tempfile.mkdtemp()
		try:
			fakedb = fakedbapi(settings=config(config_profile_path="",
				config_root=tempdir, target_root=tempdir))
			for cpv, metadata in packages:
				fakedb.cpv_inject(cpv, metadata=metadata)

			for atom, expected_result in match_tests:
				self.assertEqual( fakedb.match(atom), expected_result )
		finally:
			shutil.rmtree(tempdir)
