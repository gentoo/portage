# Copyright 2011-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import tempfile

from portage import os
from portage import shutil
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
				"USE"          : "ipc missing-iuse",
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
			("sys-apps/portage:0",                  ["sys-apps/portage-2.1.10"]),
			("sys-apps/portage:0[missing-iuse]",    []),
			("sys-apps/portage:0[-missing-iuse]",   []),
			("sys-apps/portage:0::gentoo[ipc]",     ["sys-apps/portage-2.1.10"]),
			("sys-apps/portage:0::multilib[ipc]",   []),
			("virtual/package-manager",             ["virtual/package-manager-0"]),
		)

		tempdir = tempfile.mkdtemp()
		try:
			portdir = os.path.join(tempdir, "usr/portage")
			os.makedirs(portdir)
			env = {
				"PORTDIR": portdir,
			}
			fakedb = fakedbapi(settings=config(config_profile_path="",
				env=env, eprefix=tempdir))
			for cpv, metadata in packages:
				fakedb.cpv_inject(cpv, metadata=metadata)

			for atom, expected_result in match_tests:
				result = fakedb.match(atom)
				self.assertEqual(fakedb.match(atom), expected_result,
					"fakedb.match('%s') = %s != %s" %
					(atom, result, expected_result))
		finally:
			shutil.rmtree(tempdir)
