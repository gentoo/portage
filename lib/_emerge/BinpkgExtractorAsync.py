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
import tarfile


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
		elif tarfile.is_tarfile(portage._unicode_encode(self.pkg_path,
			encoding=portage._encodings['fs'], errors='strict')):
			decomp_cmd = 'cat'
			decomp = {
				'compress': 'cat',
				'package': 'sys-apps/coreutils',
			}
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
			if decomp.get("decompress_alt"):
				decomp_cmd = decomp.get("decompress_alt")
			try:
				decompression_binary = shlex_split(varexpand(decomp_cmd, mydict=self.env))[0]
			except IndexError:
				decompression_binary = ""

			if find_binary(decompression_binary) is None:
				missing_package = decomp.get("package")
				self.scheduler.output("!!! %s\n" %
					_("File compression unsupported %s.\n Command was: %s.\n Maybe missing package: %s") %
					(self.pkg_path, varexpand(decomp_cmd, mydict=self.env), missing_package), log_path=self.logfile,
					background=self.background, level=logging.ERROR)
				self.returncode = 1
				self._async_wait()
				return

		pkg_xpak = portage.xpak.tbz2(self.pkg_path)
		pkg_xpak.scan()

		# SIGPIPE handling (128 + SIGPIPE) should be compatible with
		# assert_sigpipe_ok() that's used by the ebuild unpack() helper.
		self.args = [self._shell_binary, "-c",
			("cmd0=(head -c %d -- %s) cmd1=(%s) cmd2=(tar -xp %s -C %s -f -); " + \
			'"${cmd0[@]}" | "${cmd1[@]}" | "${cmd2[@]}"; ' + \
			"p=(${PIPESTATUS[@]}) ; for i in {0..2}; do " + \
			"if [[ ${p[$i]} != 0 && ${p[$i]} != %d ]] ; then " + \
			"echo command $(eval \"echo \\\"'\\${cmd$i[*]}'\\\"\") " + \
			"failed with status ${p[$i]} ; exit ${p[$i]} ; fi ; done; " + \
			"if [ ${p[$i]} != 0 ] ; then " + \
			"echo command $(eval \"echo \\\"'\\${cmd$i[*]}'\\\"\") " + \
			"failed with status ${p[$i]} ; exit ${p[$i]} ; fi ; " + \
			"exit 0 ;") % \
			(pkg_xpak.filestat.st_size - pkg_xpak.xpaksize,
			portage._shell_quote(self.pkg_path),
			decomp_cmd,
			tar_options,
			portage._shell_quote(self.image_dir),
			128 + signal.SIGPIPE)]

		SpawnProcess._start(self)
