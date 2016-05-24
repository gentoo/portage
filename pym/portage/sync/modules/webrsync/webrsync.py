
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


	def sync(self, **kwargs):
		'''Sync the repository'''
		if kwargs:
			self._kwargs(kwargs)

		if not self.has_bin:
			return (1, False)

		# filter these out to prevent gpg errors
		for var in ['uid', 'gid', 'groups']:
			self.spawn_kwargs.pop(var, None)

		exitcode = portage.process.spawn_bash("%s" % \
			(self.bin_command),
			**self.spawn_kwargs)
		if exitcode != os.EX_OK:
			msg = "!!! emerge-webrsync error in %s" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (exitcode, False)
		return (exitcode, True)


class PyWebRsync(SyncBase):
	'''WebRSync sync class'''

	short_desc = "Perform sync operations on webrsync based repositories"

	@staticmethod
	def name():
		return "WebRSync"


	def __init__(self):
		SyncBase.__init__(self, None, '>=sys-apps/portage-2.3')


	def sync(self, **kwargs):
		'''Sync the repository'''
		pass

