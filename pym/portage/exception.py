# Copyright 1998-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import signal
import sys
from portage import _encodings, _unicode_encode, _unicode_decode
from portage.localization import _

if sys.hexversion >= 0x3000000:
	basestring = str

class PortageException(Exception):
	"""General superclass for portage exceptions"""
	def __init__(self,value):
		self.value = value[:]
		if isinstance(self.value, basestring):
			self.value = _unicode_decode(self.value,
				encoding=_encodings['content'], errors='replace')

	def __str__(self):
		if isinstance(self.value, basestring):
			return self.value
		else:
			return _unicode_decode(repr(self.value),
				encoding=_encodings['content'], errors='replace')

	if sys.hexversion < 0x3000000:

		__unicode__ = __str__

		def __str__(self):
			return _unicode_encode(self.__unicode__(),
				encoding=_encodings['content'], errors='backslashreplace')

class CorruptionError(PortageException):
	"""Corruption indication"""

class InvalidDependString(PortageException):
	"""An invalid depend string has been encountered"""
	def __init__(self, value, errors=None):
		PortageException.__init__(self, value)
		self.errors = errors

class InvalidVersionString(PortageException):
	"""An invalid version string has been encountered"""

class SecurityViolation(PortageException):
	"""An incorrect formatting was passed instead of the expected one"""

class IncorrectParameter(PortageException):
	"""A parameter of the wrong type was passed"""

class MissingParameter(PortageException):
	"""A parameter is required for the action requested but was not passed"""

class ParseError(PortageException):
	"""An error was generated while attempting to parse the request"""

class InvalidData(PortageException):
	"""An incorrect formatting was passed instead of the expected one"""
	def __init__(self, value, category=None):
		PortageException.__init__(self, value)
		self.category = category

class InvalidDataType(PortageException):
	"""An incorrect type was passed instead of the expected one"""

class InvalidLocation(PortageException):
	"""Data was not found when it was expected to exist or was specified incorrectly"""

class FileNotFound(InvalidLocation):
	"""A file was not found when it was expected to exist"""

class DirectoryNotFound(InvalidLocation):
	"""A directory was not found when it was expected to exist"""

class OperationNotPermitted(PortageException):
	from errno import EPERM as errno
	"""An operation was not permitted operating system"""

class OperationNotSupported(PortageException):
	from errno import EOPNOTSUPP as errno
	"""Operation not supported"""

class PermissionDenied(PortageException):
	from errno import EACCES as errno
	"""Permission denied"""

class TryAgain(PortageException):
	from errno import EAGAIN as errno
	"""Try again"""

class TimeoutException(PortageException):
	"""Operation timed out"""
	# NOTE: ETIME is undefined on FreeBSD (bug #336875)
	#from errno import ETIME as errno

class AlarmSignal(TimeoutException):
	def __init__(self, value, signum=None, frame=None):
		TimeoutException.__init__(self, value)
		self.signum = signum
		self.frame = frame

	@classmethod
	def register(cls, time):
		signal.signal(signal.SIGALRM, cls._signal_handler)
		signal.alarm(time)

	@classmethod
	def unregister(cls):
		signal.alarm(0)
		signal.signal(signal.SIGALRM, signal.SIG_DFL)

	@classmethod
	def _signal_handler(cls, signum, frame):
		signal.signal(signal.SIGALRM, signal.SIG_DFL)
		raise AlarmSignal("alarm signal",
			signum=signum, frame=frame)

class ReadOnlyFileSystem(PortageException):
	"""Read-only file system"""

class CommandNotFound(PortageException):
	"""A required binary was not available or executable"""

class AmbiguousPackageName(ValueError, PortageException):
	"""Raised by portage.cpv_expand() when the package name is ambiguous due
	to the existence of multiple matches in different categories. This inherits
	from ValueError, for backward compatibility with calling code that already
	handles ValueError."""
	def __str__(self):
		return ValueError.__str__(self)

class PortagePackageException(PortageException):
	"""Malformed or missing package data"""

class PackageNotFound(PortagePackageException):
	"""Missing Ebuild or Binary"""

class PackageSetNotFound(PortagePackageException):
	"""Missing package set"""

class InvalidPackageName(PortagePackageException):
	"""Malformed package name"""

class InvalidAtom(PortagePackageException):
	"""Malformed atom spec"""
	def __init__(self, value, category=None):
		PortagePackageException.__init__(self, value)
		self.category = category

class UnsupportedAPIException(PortagePackageException):
	"""Unsupported API"""
	def __init__(self, cpv, eapi):
		self.cpv, self.eapi = cpv, eapi
	def __str__(self):
		eapi = self.eapi
		if not isinstance(eapi, basestring):
			eapi = str(eapi)
		eapi = eapi.lstrip("-")
		msg = _("Unable to do any operations on '%(cpv)s', since "
		"its EAPI is higher than this portage version's. Please upgrade"
		" to a portage version that supports EAPI '%(eapi)s'.") % \
		{"cpv": self.cpv, "eapi": eapi}
		return _unicode_decode(msg,
			encoding=_encodings['content'], errors='replace')

	if sys.hexversion < 0x3000000:

		__unicode__ = __str__

		def __str__(self):
			return _unicode_encode(self.__unicode__(),
				encoding=_encodings['content'], errors='backslashreplace')

class SignatureException(PortageException):
	"""Signature was not present in the checked file"""

class DigestException(SignatureException):
	"""A problem exists in the digest"""

class MissingSignature(SignatureException):
	"""Signature was not present in the checked file"""

class InvalidSignature(SignatureException):
	"""Signature was checked and was not a valid, current, nor trusted signature"""

class UntrustedSignature(SignatureException):
	"""Signature was not certified to the desired security level"""

