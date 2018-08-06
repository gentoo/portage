# test_NewsItem.py -- Portage Unit Testing Functionality
# Copyright 2007-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.tests import TestCase
from portage.news import NewsItem
from portage.dbapi.virtual import testdbapi
from tempfile import mkstemp
# TODO(antarus) Make newsitem use a loader so we can load using a string instead of a tempfile

class NewsItemTestCase(TestCase):
	"""These tests suck: they use your running config instead of making their own"""
	fakeItem = """
Title: YourSQL Upgrades from 4.0 to 4.1
Author: Ciaran McCreesh <ciaranm@gentoo.org>
Content-Type: text/plain
Posted: 01-Nov-2005
Revision: 1
News-Item-Format: 1.0
#Display-If-Installed:
#Display-If-Profile:
#Display-If-Arch:

YourSQL databases created using YourSQL version 4.0 are incompatible
with YourSQL version 4.1 or later. There is no reliable way to
automate the database format conversion, so action from the system
administrator is required before an upgrade can take place.

Please see the Gentoo YourSQL Upgrade Guide for instructions:

    http://www.gentoo.org/doc/en/yoursql-upgrading.xml

Also see the official YourSQL documentation:

    http://dev.yoursql.com/doc/refman/4.1/en/upgrading-from-4-0.html

After upgrading, you should also recompile any packages which link
against YourSQL:

    revdep-rebuild --library=libyoursqlclient.so.12

The revdep-rebuild tool is provided by app-portage/gentoolkit.
"""
	def setUp(self):
		self.profile = "/var/db/repos/gentoo/profiles/default-linux/x86/2007.0/"
		self.keywords = "x86"
		# Use fake/test dbapi to avoid slow tests
		self.vardb = testdbapi()
		# self.vardb.inject_cpv('sys-apps/portage-2.0', { 'SLOT' : 0 })
		# Consumers only use ARCH, so avoid portage.settings by using a dict
		self.settings = { 'ARCH' : 'x86' }

	def testDisplayIfProfile(self):
		tmpItem = self.fakeItem[:].replace("#Display-If-Profile:", "Display-If-Profile: %s" %
			self.profile)

		item = self._processItem(tmpItem)
		try:
			self.assertTrue(item.isRelevant(self.vardb, self.settings, self.profile),
				msg="Expected %s to be relevant, but it was not!" % tmpItem)
		finally:
			os.unlink(item.path)

	def testDisplayIfInstalled(self):
		tmpItem = self.fakeItem[:].replace("#Display-If-Installed:", "Display-If-Installed: %s" %
			"sys-apps/portage")

		try:
			item = self._processItem(tmpItem)
			self.assertTrue(item.isRelevant(self.vardb, self.settings, self.profile),
				msg="Expected %s to be relevant, but it was not!" % tmpItem)
		finally:
			os.unlink(item.path)

	def testDisplayIfKeyword(self):
		tmpItem = self.fakeItem[:].replace("#Display-If-Keyword:", "Display-If-Keyword: %s" %
			self.keywords)

		try:
			item = self._processItem(tmpItem)
			self.assertTrue(item.isRelevant(self.vardb, self.settings, self.profile),
				msg="Expected %s to be relevant, but it was not!" % tmpItem)
		finally:
			os.unlink(item.path)

	def _processItem(self, item):
		filename = None
		fd, filename = mkstemp()
		f = os.fdopen(fd, 'w')
		f.write(item)
		f.close()
		try:
			return NewsItem(filename, 0)
		except TypeError:
			self.fail("Error while processing news item %s" % filename)
