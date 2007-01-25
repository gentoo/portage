# gpg.py -- core Portage functionality
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$


import os
import copy
import types
import commands
import portage.exception
import portage.checksum

GPG_BINARY       = "/usr/bin/gpg"
GPG_OPTIONS      = " --lock-never --no-random-seed-file --no-greeting --no-sig-cache "
GPG_VERIFY_FLAGS = " --verify "
GPG_KEYDIR       = " --homedir '%s' "
GPG_KEYRING      = " --keyring '%s' "

UNTRUSTED = 0
EXISTS    = UNTRUSTED + 1
MARGINAL  = EXISTS    + 1
TRUSTED   = MARGINAL  + 1

def fileStats(filepath):
	mya = []
	for x in os.stat(filepath):
		mya.append(x)
	mya.append(portage.checksum.perform_checksum(filepath))
	return mya


class FileChecker:
	def __init__(self,keydir=None,keyring=None,requireSignedRing=False,minimumTrust=EXISTS):
		self.minimumTrust     = TRUSTED  # Default we require trust. For rings.
		self.keydir           = None
		self.keyring          = None
		self.keyringPath      = None
		self.keyringStats     = None
		self.keyringIsTrusted = False
	
		if (keydir != None):
			# Verify that the keydir is valid.
			if type(keydir) != types.StringType:
				raise portage.exception.InvalidDataType, "keydir argument: %s" % keydir
			if not os.path.isdir(keydir):
				raise portage.exception.DirectoryNotFound, "keydir: %s" % keydir
			self.keydir = copy.deepcopy(keydir)

		if (keyring != None):
			# Verify that the keyring is a valid filename and exists.
			if type(keyring) != types.StringType:
				raise portage.exception.InvalidDataType, "keyring argument: %s" % keyring
			if keyring.find("/") != -1:
				raise portage.exception.InvalidData, "keyring: %s" % keyring
			pathname = ""
			if keydir:
				pathname = keydir + "/" + keyring
			if not os.path.isfile(pathname):
				raise portage.exception.FileNotFound, "keyring missing: %s (dev.gentoo.org/~carpaski/gpg/)" % pathname

		keyringPath = keydir+"/"+keyring

		if not keyring or not keyringPath and requireSignedRing:
			raise portage.exception.MissingParameter

		self.keyringStats = fileStats(keyringPath)
		self.minimumTrust = TRUSTED
		if not self.verify(keyringPath, keyringPath+".asc"):
			self.keyringIsTrusted = False
			if requireSignedRing:
				raise portage.exception.InvalidSignature, "Required keyring verification: "+keyringPath
		else:
			self.keyringIsTrusted = True
		
		self.keyring      = copy.deepcopy(keyring)
		self.keyringPath  = self.keydir+"/"+self.keyring
		self.minimumTrust = minimumTrust

	def _verifyKeyring(self):
		if self.keyringStats and self.keyringPath:
			new_stats = fileStats(self.keyringPath)
			if new_stats != self.keyringStats:
				raise portage.exception.SecurityViolation, "GPG keyring changed!"

	def verify(self, filename, sigfile=None):
		"""Uses minimumTrust to determine if it is Valid/True or Invalid/False"""
		self._verifyKeyring()

		if not os.path.isfile(filename):
			raise portage.exception.FileNotFound, filename
		
		if sigfile and not os.path.isfile(sigfile):
			raise portage.exception.FileNotFound, sigfile
		
		if self.keydir and not os.path.isdir(self.keydir):
			raise portage.exception.DirectoryNotFound, filename
		
		if self.keyringPath:
			if not os.path.isfile(self.keyringPath):
				raise portage.exception.FileNotFound, self.keyringPath

		if not os.path.isfile(filename):
			raise portage.exception.CommandNotFound, filename

		command = GPG_BINARY + GPG_VERIFY_FLAGS + GPG_OPTIONS
		if self.keydir:
			command += GPG_KEYDIR % (self.keydir)
		if self.keyring:
			command += GPG_KEYRING % (self.keyring)
		
		if sigfile:
			command += " '"+sigfile+"'"
		command += " '"+filename+"'"
	
		result,output = commands.getstatusoutput(command)
		
		signal = result & 0xff
		result = (result >> 8)
	
		if signal:
			raise SignalCaught, "Signal: %d" % (signal)
	
		trustLevel     = UNTRUSTED
		if result == 0:
			trustLevel   = TRUSTED
			#if portage.output.find("WARNING") != -1:
			#	trustLevel = MARGINAL
			if portage.output.find("BAD") != -1:
				raise portage.exception.InvalidSignature, filename
		elif result == 1:
			trustLevel   = EXISTS
			if portage.output.find("BAD") != -1:
				raise portage.exception.InvalidSignature, filename
		elif result == 2:
			trustLevel   = UNTRUSTED
			if portage.output.find("could not be verified") != -1:
				raise portage.exception.MissingSignature, filename
			if portage.output.find("public key not found") != -1:
				if self.keyringIsTrusted: # We trust the ring, but not the key specifically.
					trustLevel = MARGINAL
				else:
					raise portage.exception.InvalidSignature, filename+" (Unknown Signature)"
		else:
			raise portage.exception.UnknownCondition, "GPG returned unknown result: %d" % (result)
	
		if trustLevel >= self.minimumTrust:
			return True
		return False
