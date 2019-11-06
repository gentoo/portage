# Copyright 2013-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage import shutil
from portage.util.futures import asyncio
from portage.util.futures.executor.fork import ForkExecutor
from portage.util._async.AsyncTaskFuture import AsyncTaskFuture

class FileCopier(AsyncTaskFuture):
	"""
	Asynchronously copy a file.
	"""

	__slots__ = ('src_path', 'dest_path')

	def _start(self):
		self.future = asyncio.ensure_future(self.scheduler.run_in_executor(ForkExecutor(loop=self.scheduler),
			shutil.copy, self.src_path, self.dest_path))
		super(FileCopier, self)._start()
