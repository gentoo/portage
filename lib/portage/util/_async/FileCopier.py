# Copyright 2013-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os as _os

from portage import _encodings, _unicode_encode
from portage.util import apply_stat_permissions
from portage.util.file_copy import copyfile
from portage.util.futures import asyncio
from portage.util.futures.executor.fork import ForkExecutor
from portage.util._async.AsyncTaskFuture import AsyncTaskFuture

class FileCopier(AsyncTaskFuture):
	"""
	Asynchronously copy a file.
	"""

	__slots__ = ('src_path', 'dest_path')

	def _start(self):
		self.future = asyncio.ensure_future(self.scheduler.run_in_executor(
			ForkExecutor(loop=self.scheduler), self._run))
		super(FileCopier, self)._start()

	def _run(self):
		copyfile(self.src_path, self.dest_path)
		apply_stat_permissions(self.dest_path, self.src_path.stat())
