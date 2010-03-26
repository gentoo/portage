# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AsynchronousTask import AsynchronousTask
from portage.util import writemsg
import sys
import portage
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage.package.ebuild.fetch import _checksum_failure_temp_file
import codecs

class BinpkgVerifier(AsynchronousTask):
	__slots__ = ("logfile", "pkg",)

	def _start(self):
		"""
		Note: Unlike a normal AsynchronousTask.start() method,
		this one does all work is synchronously. The returncode
		attribute will be set before it returns.
		"""

		pkg = self.pkg
		root_config = pkg.root_config
		bintree = root_config.trees["bintree"]
		rval = os.EX_OK
		stdout_orig = sys.stdout
		stderr_orig = sys.stderr
		log_file = None
		if self.background and self.logfile is not None:
			if sys.hexversion >= 0x3000000:
				# Since we are replacing the sys.std* streams,
				# we need to use the normal open() function
				# so that we get the right class (otherwise our
				# code that expects the 'buffer' attribute
				# will break).
				log_file = open(_unicode_encode(self.logfile,
					encoding=_encodings['fs'], errors='strict'),
					mode='a', encoding=_encodings['content'],
					errors='backslashreplace')
			else:
				# For python2, sys.std* are expected to be binary streams.
				log_file = open(_unicode_encode(self.logfile,
					encoding=_encodings['fs'], errors='strict'),
					mode='ab')
		try:
			if log_file is not None:
				sys.stdout = log_file
				sys.stderr = log_file
			try:
				bintree.digestCheck(pkg)
			except portage.exception.FileNotFound:
				writemsg("!!! Fetching Binary failed " + \
					"for '%s'\n" % pkg.cpv, noiselevel=-1)
				rval = 1
			except portage.exception.DigestException as e:
				writemsg("\n!!! Digest verification failed:\n",
					noiselevel=-1)
				writemsg("!!! %s\n" % e.value[0],
					noiselevel=-1)
				writemsg("!!! Reason: %s\n" % e.value[1],
					noiselevel=-1)
				writemsg("!!! Got: %s\n" % e.value[2],
					noiselevel=-1)
				writemsg("!!! Expected: %s\n" % e.value[3],
					noiselevel=-1)
				rval = 1
			if rval == os.EX_OK:
				# If this was successful, discard the log here since otherwise
				# we'll get multiple logs for the same package.
				if log_file is not None:
					try:
						os.unlink(self.logfile)
					except OSError:
						pass
			else:
				pkg_path = bintree.getname(pkg.cpv)
				head, tail = os.path.split(pkg_path)
				temp_filename = _checksum_failure_temp_file(head, tail)
				writemsg("File renamed to '%s'\n" % (temp_filename,),
					noiselevel=-1)
		finally:
			sys.stdout = stdout_orig
			sys.stderr = stderr_orig
			if log_file is not None:
				log_file.close()

		self.returncode = rval
		self.wait()

