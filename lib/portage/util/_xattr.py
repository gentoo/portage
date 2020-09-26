# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""Portability shim for xattr support

Exported API is the xattr object with get/get_all/set/remove/list operations.
We do not include the functions that Python 3.3+ provides in the os module as
the signature there is different compared to xattr.

See the standard xattr module for more documentation:
	https://pypi.python.org/pypi/pyxattr
"""

import contextlib
import os
import subprocess

from portage.exception import OperationNotSupported


class _XattrGetAll:
	"""Implement get_all() using list()/get() if there is no easy bulk method"""

	@classmethod
	def get_all(cls, item, nofollow=False, namespace=None):
		return [(name, cls.get(item, name, nofollow=nofollow, namespace=namespace))
		        for name in cls.list(item, nofollow=nofollow, namespace=namespace)]


class _XattrSystemCommands(_XattrGetAll):
	"""Implement things with getfattr/setfattr"""

	@staticmethod
	def _parse_output(output):
		for line in output.readlines():
			if line.startswith(b'#'):
				continue
			line = line.rstrip()
			if not line:
				continue
			# The lines will have the format:
			#	user.hex=0x12345
			#	user.base64=0sAQAAAgAgAAAAAAAAAAAAAAAAAAA=
			#	user.string="value0"
			# But since we don't do interpretation on the value (we just
			# save & restore it), don't bother with decoding here.
			yield line.split(b'=', 1)

	@staticmethod
	def _call(*args, **kwargs):
		proc = subprocess.Popen(*args, **kwargs)
		if proc.stdin:
			proc.stdin.close()
		proc.wait()
		return proc

	@classmethod
	def get(cls, item, name, nofollow=False, namespace=None):
		if namespace:
			name = '%s.%s' % (namespace, name)
		cmd = ['getfattr', '--absolute-names', '-n', name, item]
		if nofollow:
			cmd += ['-h']
		proc = cls._call(cmd, stdout=subprocess.PIPE)

		value = None
		for _, value in cls._parse_output(proc.stdout):
			break

		proc.stdout.close()
		return value

	@classmethod
	def set(cls, item, name, value, _flags=0, namespace=None):
		if namespace:
			name = '%s.%s' % (namespace, name)
		cmd = ['setfattr', '-n', name, '-v', value, item]
		cls._call(cmd)

	@classmethod
	def remove(cls, item, name, nofollow=False, namespace=None):
		if namespace:
			name = '%s.%s' % (namespace, name)
		cmd = ['setfattr', '-x', name, item]
		if nofollow:
			cmd += ['-h']
		cls._call(cmd)

	@classmethod
	def list(cls, item, nofollow=False, namespace=None, _names_only=True):
		cmd = ['getfattr', '-d', '--absolute-names', item]
		if nofollow:
			cmd += ['-h']
		cmd += ['-m', ('^%s[.]' % namespace) if namespace else '-']
		proc = cls._call(cmd, stdout=subprocess.PIPE)

		ret = []
		if namespace:
			namespace = '%s.' % namespace
		for name, value in cls._parse_output(proc.stdout):
			if namespace:
				if name.startswith(namespace):
					name = name[len(namespace):]
				else:
					continue
			if _names_only:
				ret.append(name)
			else:
				ret.append((name, value))

		proc.stdout.close()
		return ret

	@classmethod
	def get_all(cls, item, nofollow=False, namespace=None):
		return cls.list(item, nofollow=nofollow, namespace=namespace,
		                _names_only=False)


class _XattrStub(_XattrGetAll):
	"""Fake object since system doesn't support xattrs"""

	# pylint: disable=unused-argument

	@staticmethod
	def _raise():
		e = OSError('stub')
		e.errno = OperationNotSupported.errno
		raise e

	@classmethod
	def get(cls, item, name, nofollow=False, namespace=None):
		cls._raise()

	@classmethod
	def set(cls, item, name, value, flags=0, namespace=None):
		cls._raise()

	@classmethod
	def remove(cls, item, name, nofollow=False, namespace=None):
		cls._raise()

	@classmethod
	def list(cls, item, nofollow=False, namespace=None):
		cls._raise()


if hasattr(os, 'getxattr'):
	# Easy as pie -- active python supports it.
	class xattr(_XattrGetAll):
		"""Python >=3.3 and GNU/Linux"""

		# pylint: disable=unused-argument

		@staticmethod
		def get(item, name, nofollow=False, namespace=None):
			return os.getxattr(item, name, follow_symlinks=not nofollow)

		@staticmethod
		def set(item, name, value, flags=0, namespace=None):
			return os.setxattr(item, name, value, flags=flags)

		@staticmethod
		def remove(item, name, nofollow=False, namespace=None):
			return os.removexattr(item, name, follow_symlinks=not nofollow)

		@staticmethod
		def list(item, nofollow=False, namespace=None):
			return os.listxattr(item, follow_symlinks=not nofollow)

else:
	try:
		# Maybe we have the xattr module.
		import xattr

	except ImportError:
		try:
			# Maybe we have the attr package.
			with open(os.devnull, 'wb') as f:
				subprocess.call(['getfattr', '--version'], stdout=f)
				subprocess.call(['setfattr', '--version'], stdout=f)
			xattr = _XattrSystemCommands

		except OSError:
			# Stub it out completely.
			xattr = _XattrStub


# Add a knob so code can take evasive action as needed.
XATTRS_WORKS = xattr != _XattrStub


@contextlib.contextmanager
def preserve_xattrs(path, nofollow=False, namespace=None):
	"""Context manager to save/restore extended attributes on |path|

	If you want to rewrite a file (possibly replacing it with a new one), but
	want to preserve the extended attributes, this will do the trick.

	# First read all the extended attributes.
	with save_xattrs('/some/file'):
		... rewrite the file ...
	# Now the extended attributes are restored as needed.
	"""
	kwargs = {'nofollow': nofollow,}
	if namespace:
		# Compiled xattr python module does not like it when namespace=None.
		kwargs['namespace'] = namespace

	old_attrs = dict(xattr.get_all(path, **kwargs))
	try:
		yield
	finally:
		new_attrs = dict(xattr.get_all(path, **kwargs))
		for name, value in new_attrs.items():
			if name not in old_attrs:
				# Clear out new ones.
				xattr.remove(path, name, **kwargs)
			elif new_attrs[name] != old_attrs[name]:
				# Update changed ones.
				xattr.set(path, name, value, **kwargs)

		for name, value in old_attrs.items():
			if name not in new_attrs:
				# Re-add missing ones.
				xattr.set(path, name, value, **kwargs)
