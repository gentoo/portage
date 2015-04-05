# Copyright 2009-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import itertools
import stat
import sys

from portage.const import PORTAGE_BIN_PATH, PORTAGE_PYM_PATH, PORTAGE_PYM_PACKAGES
from portage.tests import TestCase
from portage.tests.lint.metadata import module_metadata, script_metadata
from portage import os
from portage import _encodings
from portage import _unicode_decode, _unicode_encode

class CompileModulesTestCase(TestCase):

	def testCompileModules(self):
		iters = [os.walk(os.path.join(PORTAGE_PYM_PATH, x))
			for x in PORTAGE_PYM_PACKAGES]
		iters.append(os.walk(PORTAGE_BIN_PATH))

		for parent, _dirs, files in itertools.chain(*iters):
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

				bin_path = os.path.relpath(x, PORTAGE_BIN_PATH)
				mod_path = os.path.relpath(x, PORTAGE_PYM_PATH)

				meta = module_metadata.get(mod_path) or script_metadata.get(bin_path)
				if meta:
					req_py = tuple(int(x) for x
							in meta.get('required_python', '0.0').split('.'))
					if sys.version_info < req_py:
						continue

				do_compile = False
				if x[-3:] == '.py':
					do_compile = True
				else:
					# Check for python shebang.
					try:
						with open(_unicode_encode(x,
							encoding=_encodings['fs'], errors='strict'), 'rb') as f:
							line = _unicode_decode(f.readline(),
								encoding=_encodings['content'], errors='replace')
					except IOError as e:
						# Some tests create files that are unreadable by the
						# user (by design), so ignore EACCES issues.
						if e.errno != errno.EACCES:
							raise
						continue
					if line[:2] == '#!' and 'python' in line:
						do_compile = True
				if do_compile:
					with open(_unicode_encode(x,
						encoding=_encodings['fs'], errors='strict'), 'rb') as f:
						compile(f.read(), x, 'exec')
