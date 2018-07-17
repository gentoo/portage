# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import dep_getrepo

class DepGetRepo(TestCase):
	""" A simple testcase for isvalidatom
	"""

	def testDepGetRepo(self):

		repo_char = "::"
		repos = ("a", "repo-name", "repo_name", "repo123", None)
		cpvs = ["sys-apps/portage"]
		versions = ["2.1.1", "2.1-r1", None]
		uses = ["[use]", None]
		for cpv in cpvs:
			for version in versions:
				for use in uses:
					for repo in repos:
						pkg = cpv
						if version:
							pkg = '=' + pkg + '-' + version
						if repo is not None:
							pkg = pkg + repo_char + repo
						if use:
							pkg = pkg + use
						self.assertEqual(dep_getrepo(pkg), repo)
