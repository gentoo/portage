
'''WebRsync module for portage'''

from portage.sync.syncbase import SyncBase

class WebRsync(SyncBase):
	'''WebRSync sync class'''

	short_desc = "Perform sync operations on webrsync based repositories"

	def name():
		return "WebRSync"
	name = staticmethod(name)


	def __init__(self):
		SyncBase.__init__(self, 'emerge-webrsync', '>=sys-apps/portage-2.3')


	def new(self, **kwargs):
		'''Do the initial download and install of the repository'''
		pass

	def _sync(self):
		''' Update existing repository
		'''
		pass

	def post_sync(self, portdb, location, emerge_config):
		'''repo.sync_type == "websync":
		# NOTE: Do this after reloading the config, in case
		# it did not exist prior to sync, so that the config
		# and portdb properly account for its existence.
		'''
		pass


class PyWebRsync(SyncBase):
	'''WebRSync sync class'''

	short_desc = "Perform sync operations on webrsync based repositories"

	def name():
		return "WebRSync"
	name = staticmethod(name)


	def __init__(self):
		SyncBase.__init__(self, None, '>=sys-apps/portage-2.3')


	def new(self, **kwargs):
		'''Do the initial download and install of the repository'''
		pass

	def _sync(self):
		''' Update existing repository
		'''
		pass

	def post_sync(self, portdb, location, emerge_config):
		'''repo.sync_type == "websync":
		# NOTE: Do this after reloading the config, in case
		# it did not exist prior to sync, so that the config
		# and portdb properly account for its existence.
		'''
		pass
