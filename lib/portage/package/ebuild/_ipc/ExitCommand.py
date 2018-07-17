# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.package.ebuild._ipc.IpcCommand import IpcCommand

class ExitCommand(IpcCommand):

	__slots__ = ('exitcode', 'reply_hook',)

	def __init__(self):
		IpcCommand.__init__(self)
		self.reply_hook = None
		self.exitcode = None

	def __call__(self, argv):

		if self.exitcode is not None:
			# Ignore all but the first call, since if die is called
			# then we certainly want to honor that exitcode, even
			# the ebuild process manages to send a second exit
			# command.
			self.reply_hook = None
		else:
			self.exitcode = int(argv[1])

		# (stdout, stderr, returncode)
		return ('', '', 0)
