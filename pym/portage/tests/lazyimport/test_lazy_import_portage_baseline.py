# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import re
import portage
from portage import os
from portage.tests import TestCase

from _emerge.PollScheduler import PollScheduler
from _emerge.PipeReader import PipeReader
from _emerge.SpawnProcess import SpawnProcess

class LazyImportPortageBaselineTestCase(TestCase):

	_module_re = re.compile(r'^(portage|repoman|_emerge)\.')

	_baseline_imports = frozenset([
		'portage.const', 'portage.localization',
		'portage.proxy', 'portage.proxy.lazyimport',
		'portage.proxy.objectproxy', 'portage._ensure_encodings',
	])

	_baseline_import_cmd = [portage._python_interpreter, '-c',
		'import portage, sys ; ' + \
		'sys.stdout.write(" ".join(k for k in sys.modules ' + \
		'if sys.modules[k] is not None))']

	def testLazyImportPortageBaseline(self):
		"""
		Check what modules are imported by a baseline module import.
		"""

		scheduler = PollScheduler().sched_iface
		master_fd, slave_fd = os.pipe()
		master_file = os.fdopen(master_fd, 'rb')
		slave_file = os.fdopen(slave_fd, 'wb')
		producer = SpawnProcess(
			args=self._baseline_import_cmd,
			env=os.environ, fd_pipes={1:slave_fd},
			scheduler=scheduler)
		producer.start()
		slave_file.close()

		consumer = PipeReader(
			input_files={"producer" : master_file},
			scheduler=scheduler)

		consumer.start()
		consumer.wait()
		output = consumer.getvalue().decode('ascii', 'replace').split()

		unexpected_modules = " ".join(sorted(x for x in output \
			if self._module_re.match(x) is not None and \
			x not in self._baseline_imports))

		self.assertEqual("", unexpected_modules)
