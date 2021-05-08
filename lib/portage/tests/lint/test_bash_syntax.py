# Copyright 2010-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from itertools import chain
import stat
import subprocess
import os

from portage.const import BASH_BINARY, PORTAGE_BASE_PATH, PORTAGE_BIN_PATH
from portage.tests import TestCase
from portage import _encodings

class BashSyntaxTestCase(TestCase):

	def testBashSyntax(self):
		locations = [PORTAGE_BIN_PATH]
		misc_dir = os.path.join(PORTAGE_BASE_PATH, "misc")
		if os.path.isdir(misc_dir):
			locations.append(misc_dir)
		for parent, dirs, files in \
			chain.from_iterable(os.walk(x) for x in locations):
			for x in files:
				ext = x.split('.')[-1]
				if ext in ('.py', '.pyc', '.pyo'):
					continue
				x = os.path.join(parent, x)
				st = os.lstat(x)
				if not stat.S_ISREG(st.st_mode):
					continue

				# Check for bash shebang
				f = open(x, 'rb')
				line = f.readline().decode(
					encoding=_encodings['content'], errors='replace')
				f.close()
				if line[:2] == '#!' and \
					'bash' in line:
					cmd = [str(BASH_BINARY), "-n", x]
					cmd = [x.encode(
						encoding=_encodings['fs'], errors='strict') for x in cmd]
					proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
						stderr=subprocess.STDOUT)
					output = proc.communicate()[0].decode(
						encoding=_encodings['fs'])
					status = proc.wait()
					self.assertEqual(os.WIFEXITED(status) and \
						os.WEXITSTATUS(status) == os.EX_OK, True, msg=output)
