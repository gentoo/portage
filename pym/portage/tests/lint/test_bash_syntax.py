# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import stat

from portage.const import BASH_BINARY, PORTAGE_BIN_PATH
from portage.tests import TestCase
from portage import os
from portage import subprocess_getstatusoutput
from portage import _encodings
from portage import _shell_quote
from portage import _unicode_decode, _unicode_encode

class BashSyntaxTestCase(TestCase):

	def testBashSyntax(self):
		for parent, dirs, files in os.walk(PORTAGE_BIN_PATH):
			parent = _unicode_decode(parent,
				encoding=_encodings['fs'], errors='strict')
			for x in files:
				x = _unicode_decode(x,
					encoding=_encodings['fs'], errors='strict')
				ext = x.split('.')[-1]
				if ext in ('.py', '.pyc', '.pyo'):
					continue
				x = os.path.join(parent, x)
				st = os.lstat(x)
				if not stat.S_ISREG(st.st_mode):
					continue

				# Check for bash shebang
				f = open(_unicode_encode(x,
					encoding=_encodings['fs'], errors='strict'), 'rb')
				line = _unicode_decode(f.readline(),
					encoding=_encodings['content'], errors='replace')
				f.close()
				if line[:2] == '#!' and \
					'bash' in line:
					cmd = "%s -n %s" % (_shell_quote(BASH_BINARY), _shell_quote(x))
					status, output = subprocess_getstatusoutput(cmd)
					self.assertEqual(os.WIFEXITED(status) and \
						os.WEXITSTATUS(status) == os.EX_OK, True, msg=output)
