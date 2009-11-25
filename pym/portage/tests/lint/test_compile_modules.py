# Copyright 2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.const import PORTAGE_PYM_PATH
from portage.tests import TestCase
from portage import os
from portage import _encodings
from portage import _unicode_decode

import py_compile

class CompileModulesTestCase(TestCase):

	def testCompileModules(self):
		for parent, dirs, files in os.walk(PORTAGE_PYM_PATH):
			parent = _unicode_decode(parent,
				encoding=_encodings['fs'], errors='strict')
			for x in files:
				x = _unicode_decode(x,
					encoding=_encodings['fs'], errors='strict')
				if x[-3:] == '.py':
					py_compile.compile(os.path.join(parent, x), doraise=True)
