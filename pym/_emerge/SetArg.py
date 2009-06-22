from _emerge.DependencyArg import DependencyArg
from portage.sets import SETPREFIX
class SetArg(DependencyArg):
	def __init__(self, set=None, **kwargs):
		DependencyArg.__init__(self, **kwargs)
		self.set = set
		self.name = self.arg[len(SETPREFIX):]

