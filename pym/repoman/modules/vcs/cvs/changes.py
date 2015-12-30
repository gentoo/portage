

from portage import cvstree
from repoman.modules.vcs.changes import ChangesBase

class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'cvs'

	def __init__(self, options):
		super(Changes, self).__init__(options)

	def _scan(self):
		tree = cvstree.getentries("./", recursive=1)
		self.changed = cvstree.findchanged(tree, recursive=1, basedir="./")
		self.new = cvstree.findnew(tree, recursive=1, basedir="./")
		if self.options.if_modified == "y":
			self.removed = cvstree.findremoved(tree, recursive=1, basedir="./")
		del tree
