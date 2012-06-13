# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import datetime
import subprocess
import sys
import tempfile
import time

import portage
from portage import os
from portage import shutil
from portage.tests import TestCase
from repoman.utilities import UpdateChangeLog

class RepomanEchangelogTestCase(TestCase):

	def setUp(self):
		super(RepomanEchangelogTestCase, self).setUp()

		self.tmpdir = tempfile.mkdtemp(prefix='repoman.echangelog.')

		self.skel_changelog = os.path.join(self.tmpdir, 'skel.ChangeLog')
		skel = [
			'# ChangeLog for <CATEGORY>/<PACKAGE_NAME>\n',
			'# Copyright 1999-2000 Gentoo Foundation; Distributed under the GPL v2\n',
			'# $Header: $\n'
		]
		self._writelines(self.skel_changelog, skel)

		self.cat = 'mycat'
		self.pkg = 'mypkg'
		self.pkgdir = os.path.join(self.tmpdir, self.cat, self.pkg)
		os.makedirs(self.pkgdir)

		self.header_pkg = '# ChangeLog for %s/%s\n' % (self.cat, self.pkg)
		self.header_copyright = '# Copyright 1999-%s Gentoo Foundation; Distributed under the GPL v2\n' % \
			datetime.datetime.now().year
		self.header_cvs = '# $Header: $\n'

		self.changelog = os.path.join(self.pkgdir, 'ChangeLog')

		self.user = 'Testing User <portage@gentoo.org>'

	def tearDown(self):
		super(RepomanEchangelogTestCase, self).tearDown()
		shutil.rmtree(self.tmpdir)

	def _readlines(self, file):
		with open(file, 'r') as f:
			return f.readlines()

	def _writelines(self, file, data):
		with open(file, 'w') as f:
			f.writelines(data)

	def testRejectRootUser(self):
		self.assertEqual(UpdateChangeLog(self.pkgdir, 'me <root@gentoo.org>', '', '', '', '', quiet=True), None)

	def testMissingSkelFile(self):
		# Test missing ChangeLog, but with empty skel (i.e. do nothing).
		UpdateChangeLog(self.pkgdir, self.user, 'test!', '/does/not/exist', self.cat, self.pkg, quiet=True)
		actual_cl = self._readlines(self.changelog)
		self.assertTrue(len(actual_cl[0]) > 0)

	def testEmptyChangeLog(self):
		# Make sure we do the right thing with a 0-byte ChangeLog
		open(self.changelog, 'w').close()
		UpdateChangeLog(self.pkgdir, self.user, 'test!', self.skel_changelog, self.cat, self.pkg, quiet=True)
		actual_cl = self._readlines(self.changelog)
		self.assertEqual(actual_cl[0], self.header_pkg)
		self.assertEqual(actual_cl[1], self.header_copyright)
		self.assertEqual(actual_cl[2], self.header_cvs)

	def testCopyrightUpdate(self):
		# Make sure updating the copyright line works
		UpdateChangeLog(self.pkgdir, self.user, 'test!', self.skel_changelog, self.cat, self.pkg, quiet=True)
		actual_cl = self._readlines(self.changelog)
		self.assertEqual(actual_cl[1], self.header_copyright)

	def testSkelHeader(self):
		# Test skel.ChangeLog -> ChangeLog
		UpdateChangeLog(self.pkgdir, self.user, 'test!', self.skel_changelog, self.cat, self.pkg, quiet=True)
		actual_cl = self._readlines(self.changelog)
		self.assertEqual(actual_cl[0], self.header_pkg)
		self.assertNotEqual(actual_cl[-1], '\n')

	def testExistingGoodHeader(self):
		# Test existing ChangeLog (correct values)
		self._writelines(self.changelog, [self.header_pkg])

		UpdateChangeLog(self.pkgdir, self.user, 'test!', self.skel_changelog, self.cat, self.pkg, quiet=True)
		actual_cl = self._readlines(self.changelog)
		self.assertEqual(actual_cl[0], self.header_pkg)

	def testExistingBadHeader(self):
		# Test existing ChangeLog (wrong values)
		self._writelines(self.changelog, ['# ChangeLog for \n'])

		UpdateChangeLog(self.pkgdir, self.user, 'test!', self.skel_changelog, self.cat, self.pkg, quiet=True)
		actual_cl = self._readlines(self.changelog)
		self.assertEqual(actual_cl[0], self.header_pkg)

	def testTrailingNewlines(self):
		# Make sure trailing newlines get chomped.
		self._writelines(self.changelog, ['#\n', 'foo\n', '\n', 'bar\n', '\n', '\n'])

		UpdateChangeLog(self.pkgdir, self.user, 'test!', self.skel_changelog, self.cat, self.pkg, quiet=True)
		actual_cl = self._readlines(self.changelog)
		self.assertNotEqual(actual_cl[-1], '\n')
