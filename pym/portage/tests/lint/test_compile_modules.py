# Copyright 2009-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import itertools
import stat

from portage.const import PORTAGE_BIN_PATH, PORTAGE_PYM_PATH
from portage.tests import TestCase
from portage import os
from portage import _encodings
from portage import _unicode_decode, _unicode_encode

import py_compile

class CompileModulesTestCase(TestCase):

	def testCompileModules(self):
		for parent, dirs, files in itertools.chain(
			os.walk(PORTAGE_BIN_PATH),
			os.walk(PORTAGE_PYM_PATH)):
			parent = _unicode_decode(parent,
				encoding=_encodings['fs'], errors='strict')
			for x in files:
				x = _unicode_decode(x,
					encoding=_encodings['fs'], errors='strict')
				if x[-4:] in ('.pyc', '.pyo'):
					continue
				x = os.path.join(parent, x)
				st = os.lstat(x)
				if not stat.S_ISREG(st.st_mode):
					continue
				do_compile = False
				if x[-3:] == '.py':
					do_compile = True
				else:
					# Check for python shebang
					f = open(_unicode_encode(x,
						encoding=_encodings['fs'], errors='strict'), 'rb')
					line = _unicode_decode(f.readline(),
						encoding=_encodings['content'], errors='replace')
					f.close()
					if line[:2] == '#!' and \
						'python' in line:
						do_compile = True
				if do_compile:
					py_compile.compile(x, cfile='/dev/null', doraise=True)
