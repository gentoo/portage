# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging

from _emerge.SpawnProcess import SpawnProcess
import portage
from portage.localization import _
from portage.util.compression_probe import (
	compression_probe,
	_compressors,
)
from portage.process import find_binary
from portage.util import (
	shlex_split,
	varexpand,
)
import signal
import subprocess

class BinpkgExtractorAsync(SpawnProcess):

	__slots__ = ("features", "image_dir", "pkg", "pkg_path")

	_shell_binary = portage.const.BASH_BINARY

	def _start(self):
		tar_options = ""
		if "xattr" in self.features:
			process = subprocess.Popen(["tar", "--help"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
			output = process.communicate()[0]
			if b"--xattrs" in output:
				tar_options = ["--xattrs", "--xattrs-include='*'"]
				for x in portage.util.shlex_split(self.env.get("PORTAGE_XATTR_EXCLUDE", "")):
					tar_options.append(portage._shell_quote("--xattrs-exclude=%s" % x))
				tar_options = " ".join(tar_options)

		decomp = _compressors.get(compression_probe(self.pkg_path))
		if decomp is not None:
			decomp_cmd = decomp.get("decompress")
		else:
			decomp_cmd = None
		if decomp_cmd is None:
			self.scheduler.output("!!! %s\n" %
				_("File compression header unrecognized: %s") %
				self.pkg_path, log_path=self.logfile,
				background=self.background, level=logging.ERROR)
			self.returncode = 1
			self._async_wait()
			return

		try:
			decompression_binary = shlex_split(varexpand(decomp_cmd, mydict=self.env))[0]
		except IndexError:
			decompression_binary = ""

		if find_binary(decompression_binary) is None:
			# Try alternative command if it exists
			if _compressors.get(compression_probe(self.pkg_path)).get("decompress_alt"):
				decomp_cmd = _compressors.get(
					compression_probe(self.pkg_path)).get("decompress_alt")
			try:
				decompression_binary = shlex_split(varexpand(decomp_cmd, mydict=self.env))[0]
			except IndexError:
				decompression_binary = ""

			if find_binary(decompression_binary) is None:
				missing_package = _compressors.get(compression_probe(self.pkg_path)).get("package")
				self.scheduler.output("!!! %s\n" %
					_("File compression unsupported %s.\n Command was: %s.\n Maybe missing package: %s") %
					(self.pkg_path, varexpand(decomp_cmd, mydict=self.env), missing_package), log_path=self.logfile,
					background=self.background, level=logging.ERROR)
				self.returncode = 1
				self._async_wait()
				return

		# Add -q to decomp_cmd opts, in order to avoid "trailing garbage
		# after EOF ignored" warning messages due to xpak trailer.
		# SIGPIPE handling (128 + SIGPIPE) should be compatible with
		# assert_sigpipe_ok() that's used by the ebuild unpack() helper.
		self.args = [self._shell_binary, "-c",
			("%s -cq -- %s | tar -xp %s -C %s -f - ; " + \
			"p=(${PIPESTATUS[@]}) ; " + \
			"if [[ ${p[0]} != 0 && ${p[0]} != %d ]] ; then " % (128 + signal.SIGPIPE) + \
			"echo bzip2 failed with status ${p[0]} ; exit ${p[0]} ; fi ; " + \
			"if [ ${p[1]} != 0 ] ; then " + \
			"echo tar failed with status ${p[1]} ; exit ${p[1]} ; fi ; " + \
			"exit 0 ;") % \
			(decomp_cmd,
			portage._shell_quote(self.pkg_path),
			tar_options,
			portage._shell_quote(self.image_dir))]

		SpawnProcess._start(self)
