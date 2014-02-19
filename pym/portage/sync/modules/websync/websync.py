
'''WebRsync module for portage'''

class WebRsync(object):
	'''WebRSync sync class'''

	short_desc = "Perform sync operations on webrsync based repositories"

	def name():
		return "WebRSync"
	name = staticmethod(name)


	def can_progressbar(self, func):
		return False


	def __init__(self):
		self.options = None
		self.settings = None
		self.logger = None
		self.repo = None
		self.xterm_titles = None

		self.has_git = True
		if portage.process.find_binary("emerge-webrsync") is None:
			msg = ["Command not found: git",
			"Type \"emerge %s\" to enable git support." % portage.const.GIT_PACKAGE_ATOM]
			for l in msg:
				writemsg_level("!!! %s\n" % l,
					level=logging.ERROR, noiselevel=-1)
			self.has_git = False


	def _kwargs(self, kwargs):
		'''Sets internal variables from kwargs'''
		self.options = kwargs.get('options', {})
		self.settings = self.options.get('settings', None)
		self.logger = self.options.get('logger', None)
		self.repo = self.options.get('repo', None)
		self.xterm_titles = self.options.get('xterm_titles', False)


	def exists(self, **kwargs):
		'''Tests whether the repo actually exists'''
		if kwargs:
			self._kwargs(kwargs)
		elif not self.repo:
			return False
		spawn_kwargs = self.options.get('spawn_kwargs', None)

		if not os.path.exists(self.repo.location):
			return False
		return True


	def sync(self, **kwargs):
		'''Sync the repository'''
		if kwargs:
			self._kwargs(kwargs)

		if not self.has_git:
			return (1, False)

		if not self.exists():
			return self.new()
		return self._sync()


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


class PyWebRsync(object):
	'''WebRSync sync class'''

	short_desc = "Perform sync operations on webrsync based repositories"

	def name():
		return "WebRSync"
	name = staticmethod(name)


	def can_progressbar(self, func):
		return False


	def __init__(self):
		self.options = None
		self.settings = None
		self.logger = None
		self.repo = None
		self.xterm_titles = None

		#if portage.process.find_binary("gpg") is None:
			#msg = ["Command not found: gpg",
			#"Type \"emerge %s\" to enable blah support." % 'emerge-webrsync']
			#for l in msg:
				#writemsg_level("!!! %s\n" % l,
				#	level=logging.ERROR, noiselevel=-1)


	def _kwargs(self, kwargs):
		'''Sets internal variables from kwargs'''
		self.options = kwargs.get('options', {})
		self.settings = self.options.get('settings', None)
		self.logger = self.options.get('logger', None)
		self.repo = self.options.get('repo', None)
		self.xterm_titles = self.options.get('xterm_titles', False)


	def exists(self, **kwargs):
		'''Tests whether the repo actually exists'''
		if kwargs:
			self._kwargs(kwargs)
		elif not self.repo:
			return False
		spawn_kwargs = self.options.get('spawn_kwargs', None)

		if not os.path.exists(self.repo.location):
			return False
		return True


	def sync(self, **kwargs):
		'''Sync/Clone the repository'''
		if kwargs:
			self._kwargs(kwargs)

		if not self.has_git:
			return (1, False)

		if not self.exists():
			return self.new()
		return self._sync()


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
