# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage import shutil
from portage.util._async.ForkProcess import ForkProcess

class FileCopier(ForkProcess):
	"""
	Asynchronously copy a file.
	"""

	__slots__ = ('src_path', 'dest_path')

	def _run(self):
		shutil.copy(self.src_path, self.dest_path)
		return os.EX_OK
