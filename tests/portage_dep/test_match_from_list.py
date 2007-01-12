# test_match_from_list.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from unittest import TestCase
from portage_dep import match_from_list

class AtomCmpEqualGlob(TestCase):
        """ A simple testcase for =* glob matching
        """

        def testEqualGlobPass(self):
                tests = [ ("=sys-apps/portage-45*", "sys-apps/portage-045" ),
                          ("=sys-fs/udev-1*", "sys-fs/udev-123"),
                          ("=sys-fs/udev-4*", "sys-fs/udev-456" ) ]

# I need to look up the cvs syntax
#                         ("=sys-fs/udev_cvs*","sys-fs/udev_cvs_pre4" ) ]

                for test in tests:
                        self.assertEqual( len(match_from_list( test[0], [test[1]] )), 1 )

        def testEqualGlobFail(self):
                tests = [ ("=sys-apps/portage-2*", "sys-apps/portage-2.1" ),
                          ("=sys-apps/portage-2.1*", "sys-apps/portage-2.1.2" ) ]
                for test in tests:
                        try:
                                self.assertEqual( len( match_from_list( test[0], [test[1]] ) ), 1 )
                        except TypeError: # failure is ok here
                                pass
