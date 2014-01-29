# Copyright 1999-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys
import logging
import errno

import portage
from portage import os
from portage.util import writemsg_level


class CVSSync(object):
	'''CVS sync module'''

	short_desc = "Perform sync operations on rsync based repositories"

	@staticmethod
	def name():
		return "CVSSync"


	def can_progressbar(self, func):
		return False


	def __init__(self):
		self.settings = None


	def sync(self, **kwargs):
		'''repo.sync_type == "cvs":'''

		if not os.path.exists("/usr/bin/cvs"):
			print("!!! /usr/bin/cvs does not exist, so CVS support is disabled.")
			print("!!! Type \"emerge %s\" to enable CVS support." % portage.const.CVS_PACKAGE_ATOM)
			return os.EX_UNAVAILABLE

		if kwargs:
			options = kwargs.get('options', {})
			repo = options.get('repo', None)
			spawn_kwargs = options.get('spawn_kwargs', None)

		cvs_root = repo.sync_uri
		if cvs_root.startswith("cvs://"):
			cvs_root = cvs_root[6:]
		if not os.path.exists(os.path.join(repo.location, "CVS")):
			#initial checkout
			print(">>> Starting initial cvs checkout with "+repo.sync_uri+"...")
			try:
				os.rmdir(repo.location)
			except OSError as e:
				if e.errno != errno.ENOENT:
					sys.stderr.write(
						"!!! existing '%s' directory; exiting.\n" % repo.location)
					exitcode = 1
					return self.post_sync(repo.location, exitcode)
				del e
			if portage.process.spawn_bash(
					"cd %s; exec cvs -z0 -d %s co -P -d %s %s" %
					(portage._shell_quote(os.path.dirname(repo.location)), portage._shell_quote(cvs_root),
					portage._shell_quote(os.path.basename(repo.location)), portage._shell_quote(repo.sync_cvs_repo)),
					**portage._native_kwargs(spawn_kwargs)) != os.EX_OK:
				print("!!! cvs checkout error; exiting.")
				exitcode = 1
		else:
			#cvs update
			print(">>> Starting cvs update with "+repo.sync_uri+"...")
			exitcode = portage.process.spawn_bash(
				"cd %s; exec cvs -z0 -q update -dP" % \
				(portage._shell_quote(repo.location),),
				**portage._native_kwargs(spawn_kwargs))
			if exitcode != os.EX_OK:
				writemsg_level("!!! cvs update error; exiting.\n",
					noiselevel=-1, level=logging.ERROR)
		return self.post_sync(repo.location, exitcode)


	def post_sync(self, location, exitcode):
		return location, exitcode, False
