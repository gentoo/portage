# test_NewsItem.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_varExpand.py 5596 2007-01-12 08:08:53Z antarus $

from portage.tests import TestCase, TestLoader
from portage.news import NewsItem
from portage.const import PROFILE_PATH

class NewsItemTestCase(TestCase):
	
	self.fakeItem = """
Title: YourSQL Upgrades from 4.0 to 4.1
Author: Ciaran McCreesh <ciaranm@gentoo.org>
Content-Type: text/plain
Posted: 01-Nov-2005
Revision: 1
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

	from portage import settings
	import time

	def testDisplayIfProfile():
		from portage.const import PROFILE_PATH
		tmpItem = self.fakeItem.replace("#Display-If-Profile:", "Display-If-Profile: %s" %
			os.readlink( PROFILE_PATH ) )

		item = _processItem(tmpItem)
		self.assertTrue( item.isRelevant( os.readlink( PROFILE_PATH ) ),
			msg="Expected %s to be relevant, but it was not!" % tmpItem )

	def testDisplayIfInstalled():
		tmpItem = self.fakeItem.replace("#Display-If-Installed:", "Display-If-Profile: %s" %
			"sys-apps/portage" )

		item = _processItem(tmpItem)
		self.assertTrue( item.isRelevant( portage.settings ),
			msg="Expected %s to be relevant, but it was not!" % tmpItem )


	def testDisplayIfKeyword():
		from portage import settings
		tmpItem = self.fakeItem.replace("#Display-If-Keyword:", "Display-If-Keyword: %s" %
			settings["ACCEPT_KEYWORDS"].split()[0] )

		item = _processItem(tmpItem)
		self.assertTrue( item.isRelevant( os.readlink( PROFILE_PATH ) ),
			msg="Expected %s to be relevant, but it was not!" % tmpItem )
		

	def _processItem( self, item ):

		path = os.path.join( settings["PORTAGE_TMPDIR"], str(time.time())
		f = open( os.path.join( path )
		f.write(item)
		f.close
		try:
			return NewsItem( path, 0 )
		except TypeError:
			self.fail("Error while processing news item %s" % path )
