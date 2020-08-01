#!/usr/bin/python -b
# Copyright 2011-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Helper tool for converting installed files to custom prefixes.

In other words, eprefixy $D for Gentoo/Prefix."""
__doc__ = doc

import argparse
import io
import os
import stat
import sys

CONTENT_ENCODING = 'utf_8'
FS_ENCODING = 'utf_8'

try:
	import magic
except ImportError:
	magic = None
else:
	try:
		magic.MIME_TYPE
	except AttributeError:
		# magic module seems to be broken
		magic = None

class IsTextFile:

	def __init__(self):
		if magic is not None:
			self._call = self._is_text_magic
			self._m = magic.open(magic.MIME_TYPE)
			self._m.load()
		else:
			self._call = self._is_text_encoding
			self._encoding = CONTENT_ENCODING

	def __call__(self, filename):
		"""
		Returns True if the given file is a text file, and False otherwise.
		"""
		return self._call(filename)

	def _is_text_magic(self, filename):
		mime_type = self._m.file(filename)
		if isinstance(mime_type, bytes):
			mime_type = mime_type.decode('ascii', 'replace')
		return mime_type.startswith('text/')

	def _is_text_encoding(self, filename):
		try:
			for line in io.open(filename, mode='r', encoding=self._encoding):
				pass
		except UnicodeDecodeError:
			return False
		return True

def chpath_inplace(filename, is_text_file, old, new):
	"""
	Returns True if any modifications were made, and False otherwise.
	"""

	modified = False
	orig_stat = os.lstat(filename)
	try:
		f = io.open(filename, buffering=0, mode='r+b')
	except IOError:
		try:
			orig_mode = stat.S_IMODE(os.lstat(filename).st_mode)
		except OSError as e:
			sys.stderr.write('%s: %s\n' % (e, filename))
			return
		temp_mode = 0o200 | orig_mode
		os.chmod(filename, temp_mode)
		try:
			f = io.open(filename, buffering=0, mode='r+b')
		finally:
			os.chmod(filename, orig_mode)

	len_old = len(old)
	len_new = len(new)
	matched_byte_count = 0
	while True:
		in_byte = f.read(1)

		if not in_byte:
			break

		if in_byte == old[matched_byte_count:matched_byte_count+1]:
			matched_byte_count += 1
			if matched_byte_count == len_old:
				modified = True
				matched_byte_count = 0
				end_position = f.tell()
				start_position = end_position - len_old
				if not is_text_file:
					# search backwards for leading slashes written by
					# a previous invocation of this tool
					num_to_write = len_old
					f.seek(start_position - 1)
					while True:
						if f.read(1) != b'/':
							break
						num_to_write += 1
						f.seek(f.tell() - 2)

					# pad with as many leading slashes as necessary
					while num_to_write > len_new:
						f.write(b'/')
						num_to_write -= 1
					f.write(new)
				else:
					remainder = f.read()
					f.seek(start_position)
					f.write(new)
					if remainder:
						f.write(remainder)
						f.truncate()
						f.seek(start_position + len_new)
		elif matched_byte_count > 0:
			# back up an try to start a new match after
			# the first byte of the previous partial match
			f.seek(f.tell() - matched_byte_count)
			matched_byte_count = 0

	f.close()
	if modified:
		orig_mtime = orig_stat.st_mtime_ns
		os.utime(filename, ns=(orig_mtime, orig_mtime))
	return modified

def chpath_inplace_symlink(filename, st, old, new):
	target = os.readlink(filename)
	if target.startswith(old):
		new_target = new + target[len(old):]
		os.unlink(filename)
		os.symlink(new_target, filename)
		os.lchown(filename, st.st_uid, st.st_gid)

def main(argv):

	parser = argparse.ArgumentParser(description=doc)
	parser.add_argument('location', default=None,
		help='root directory (e.g. $D)')
	parser.add_argument('old', default=None,
		help='original build prefix (e.g. /)')
	parser.add_argument('new', default=None,
		help='new install prefix (e.g. $EPREFIX)')
	opts = parser.parse_args(argv)

	location, old, new = opts.location, opts.old, opts.new

	is_text_file = IsTextFile()

	if not isinstance(location, bytes):
		location = location.encode(FS_ENCODING)
	if not isinstance(old, bytes):
		old = old.encode(FS_ENCODING)
	if not isinstance(new, bytes):
		new = new.encode(FS_ENCODING)

	st = os.lstat(location)

	if stat.S_ISDIR(st.st_mode):
		for parent, dirs, files in os.walk(location):
			for filename in files:
				filename = os.path.join(parent, filename)
				try:
					st = os.lstat(filename)
				except OSError:
					pass
				else:
					if stat.S_ISREG(st.st_mode):
						chpath_inplace(filename,
							is_text_file(filename), old, new)
					elif stat.S_ISLNK(st.st_mode):
						chpath_inplace_symlink(filename, st, old, new)

	elif stat.S_ISREG(st.st_mode):
		chpath_inplace(location,
			is_text_file(location), old, new)
	elif stat.S_ISLNK(st.st_mode):
		chpath_inplace_symlink(location, st, old, new)

	return os.EX_OK

if __name__ == '__main__':
	sys.exit(main(sys.argv[1:]))
