# -*- coding:utf-8 -*-

from __future__ import print_function

import errno
import logging
import subprocess
import sys

import portage
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage.exception import MissingParameter
from portage.process import find_binary


# Setup the GPG commands
def gpgsign(filename, repoman_settings, options):
	gpgcmd = repoman_settings.get("PORTAGE_GPG_SIGNING_COMMAND")
	if gpgcmd in [None, '']:
		raise MissingParameter("PORTAGE_GPG_SIGNING_COMMAND is unset!"
			" Is make.globals missing?")
	if "${PORTAGE_GPG_KEY}" in gpgcmd and \
		"PORTAGE_GPG_KEY" not in repoman_settings:
		raise MissingParameter("PORTAGE_GPG_KEY is unset!")
	if "${PORTAGE_GPG_DIR}" in gpgcmd:
		if "PORTAGE_GPG_DIR" not in repoman_settings:
			repoman_settings["PORTAGE_GPG_DIR"] = \
				os.path.expanduser("~/.gnupg")
			logging.info(
				"Automatically setting PORTAGE_GPG_DIR to '%s'" %
				repoman_settings["PORTAGE_GPG_DIR"])
		else:
			repoman_settings["PORTAGE_GPG_DIR"] = \
				os.path.expanduser(repoman_settings["PORTAGE_GPG_DIR"])
		if not os.access(repoman_settings["PORTAGE_GPG_DIR"], os.X_OK):
			raise portage.exception.InvalidLocation(
				"Unable to access directory: PORTAGE_GPG_DIR='%s'" %
				repoman_settings["PORTAGE_GPG_DIR"])
	gpgvars = {"FILE": filename}
	for k in ("PORTAGE_GPG_DIR", "PORTAGE_GPG_KEY"):
		v = repoman_settings.get(k)
		if v is not None:
			gpgvars[k] = v
	gpgcmd = portage.util.varexpand(gpgcmd, mydict=gpgvars)
	if options.pretend:
		print("(" + gpgcmd + ")")
	else:
		# Encode unicode manually for bug #310789.
		gpgcmd = portage.util.shlex_split(gpgcmd)

		gpgcmd = [
			_unicode_encode(arg, encoding=_encodings['fs'], errors='strict')
			for arg in gpgcmd]
		rValue = subprocess.call(gpgcmd)
		if rValue == os.EX_OK:
			os.rename(filename + ".asc", filename)
		else:
			raise portage.exception.PortageException(
				"!!! gpg exited with '" + str(rValue) + "' status")

def need_signature(filename):
	try:
		with open(
			_unicode_encode(
				filename, encoding=_encodings['fs'], errors='strict'),
			'rb') as f:
			return b"BEGIN PGP SIGNED MESSAGE" not in f.readline()
	except IOError as e:
		if e.errno in (errno.ENOENT, errno.ESTALE):
			return False
		raise
