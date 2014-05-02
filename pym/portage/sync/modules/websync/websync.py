
'''WebRsync module for portage'''

import logging

import portage
from portage import os
from portage.util import writemsg_level
from portage.output import create_color_func
good = create_color_func("GOOD")
bad = create_color_func("BAD")
warn = create_color_func("WARN")
from portage.sync.syncbase import SyncBase


class WebRsync(SyncBase):
	'''WebRSync sync class'''

	short_desc = "Perform sync operations on webrsync based repositories"

	@staticmethod
	def name():
		return "WebRSync"


	def __init__(self):
		SyncBase.__init__(self, 'emerge-webrsync', '>=sys-apps/portage-2.3')


	def new(self, **kwargs):
		'''Do the initial download and install of the repository'''
		return self._sync()


	def _sync(self):
		''' Update existing repository
		'''
		emerge_config = self.options.get('emerge_config', None)
		portdb = self.options.get('portdb', None)

		msg = ">>> Starting emerge-webrsync for %s..." % self.repo.location
		self.logger(self.xterm_titles, msg)
		writemsg_level(msg + "\n")
		exitcode = portage.process.spawn_bash("%s" % \
			(self.bin_command),
			**portage._native_kwargs(self.spawn_kwargs))
		if exitcode != os.EX_OK:
			msg = "!!! emerge-webrsync error in %s" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (exitcode, False)
		msg = ">>> Emerge-webrsync successful: %s" % self.repo.location
		self.logger(self.xterm_titles, msg)
		writemsg_level(msg + "\n")
		#return self.post_sync(portdb, self.repo.location, emerge_config)
		return (exitcode, True)


class PyWebRsync(SyncBase):
	'''WebRSync sync class'''

	short_desc = "Perform sync operations on webrsync based repositories"

	@staticmethod
	def name():
		return "WebRSync"


	def __init__(self):
		SyncBase.__init__(self, None, '>=sys-apps/portage-2.3')


	def new(self, **kwargs):
		'''Do the initial download and install of the repository'''
		pass


	def _sync(self):
		''' Update existing repository
		'''
		pass
