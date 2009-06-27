class DependencyArg(object):
	def __init__(self, arg=None, root_config=None):
		self.arg = arg
		self.root_config = root_config

	def __str__(self):
		return str(self.arg)

