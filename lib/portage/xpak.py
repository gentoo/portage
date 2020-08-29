# Copyright 2001-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2


# The format for a tbz2/xpak:
#
#  tbz2: tar.bz2 + xpak + (xpak_offset) + "STOP"
#  xpak: "XPAKPACK" + (index_len) + (data_len) + index + data + "XPAKSTOP"
# index: (pathname_len) + pathname + (data_offset) + (data_len)
#        index entries are concatenated end-to-end.
#  data: concatenated data chunks, end-to-end.
#
# [tarball]XPAKPACKIIIIDDDD[index][data]XPAKSTOPOOOOSTOP
#
# (integer) == encodeint(integer)  ===> 4 characters (big-endian copy)
# '+' means concatenate the fields ===> All chunks are strings

__all__ = [
	'addtolist', 'decodeint', 'encodeint', 'getboth',
	'getindex', 'getindex_mem', 'getitem', 'listindex',
	'searchindex', 'tbz2', 'xpak_mem', 'xpak', 'xpand',
	'xsplit', 'xsplit_mem',
]

import array
import errno

import portage
from portage import os
from portage import shutil
from portage import normalize_path
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.util.file_copy import copyfile

def addtolist(mylist, curdir):
	"""(list, dir) --- Takes an array(list) and appends all files from dir down
	the directory tree. Returns nothing. list is modified."""
	curdir = normalize_path(_unicode_decode(curdir,
		encoding=_encodings['fs'], errors='strict'))
	for parent, dirs, files in os.walk(curdir):

		parent = _unicode_decode(parent,
			encoding=_encodings['fs'], errors='strict')
		if parent != curdir:
			mylist.append(parent[len(curdir) + 1:] + os.sep)

		for x in dirs:
			try:
				_unicode_decode(x, encoding=_encodings['fs'], errors='strict')
			except UnicodeDecodeError:
				dirs.remove(x)

		for x in files:
			try:
				x = _unicode_decode(x,
					encoding=_encodings['fs'], errors='strict')
			except UnicodeDecodeError:
				continue
			mylist.append(os.path.join(parent, x)[len(curdir) + 1:])

def encodeint(myint):
	"""Takes a 4 byte integer and converts it into a string of 4 characters.
	Returns the characters in a string."""
	a = array.array('B')
	a.append((myint >> 24) & 0xff)
	a.append((myint >> 16) & 0xff)
	a.append((myint >>  8) & 0xff)
	a.append(myint & 0xff)
	try:
		# Python >= 3.2
		return a.tobytes()
	except AttributeError:
		return a.tostring()

def decodeint(mystring):
	"""Takes a 4 byte string and converts it into a 4 byte integer.
	Returns an integer."""
	myint = 0
	myint += mystring[3]
	myint += mystring[2] << 8
	myint += mystring[1] << 16
	myint += mystring[0] << 24
	return myint

def xpak(rootdir, outfile=None):
	"""(rootdir, outfile) -- creates an xpak segment of the directory 'rootdir'
	and under the name 'outfile' if it is specified. Otherwise it returns the
	xpak segment."""

	mylist = []

	addtolist(mylist, rootdir)
	mylist.sort()
	mydata = {}
	for x in mylist:
		if x == 'CONTENTS':
			# CONTENTS is generated during the merge process.
			continue
		x = _unicode_encode(x, encoding=_encodings['fs'], errors='strict')
		with open(os.path.join(rootdir, x), 'rb') as f:
			mydata[x] = f.read()

	xpak_segment = xpak_mem(mydata)
	if outfile:
		outf = open(_unicode_encode(outfile,
			encoding=_encodings['fs'], errors='strict'), 'wb')
		outf.write(xpak_segment)
		outf.close()
	else:
		return xpak_segment

def xpak_mem(mydata):
	"""Create an xpack segment from a map object."""

	mydata_encoded = {}
	for k, v in mydata.items():
		k = _unicode_encode(k,
			encoding=_encodings['repo.content'], errors='backslashreplace')
		v = _unicode_encode(v,
			encoding=_encodings['repo.content'], errors='backslashreplace')
		mydata_encoded[k] = v
	mydata = mydata_encoded
	del mydata_encoded

	indexglob = b''
	indexpos = 0
	dataglob = b''
	datapos = 0
	for x, newglob in mydata.items():
		mydatasize = len(newglob)
		indexglob = indexglob + encodeint(len(x)) + x + encodeint(datapos) + encodeint(mydatasize)
		indexpos = indexpos + 4 + len(x) + 4 + 4
		dataglob = dataglob + newglob
		datapos = datapos + mydatasize
	return b'XPAKPACK' \
		+ encodeint(len(indexglob)) \
		+ encodeint(len(dataglob)) \
		+ indexglob \
		+ dataglob \
		+ b'XPAKSTOP'

def xsplit(infile):
	"""(infile) -- Splits the infile into two files.
	'infile.index' contains the index segment.
	'infile.dat' contails the data segment."""
	infile = _unicode_decode(infile,
		encoding=_encodings['fs'], errors='strict')
	myfile = open(_unicode_encode(infile,
		encoding=_encodings['fs'], errors='strict'), 'rb')
	mydat = myfile.read()
	myfile.close()

	splits = xsplit_mem(mydat)
	if not splits:
		return False

	myfile = open(_unicode_encode(infile + '.index',
		encoding=_encodings['fs'], errors='strict'), 'wb')
	myfile.write(splits[0])
	myfile.close()
	myfile = open(_unicode_encode(infile + '.dat',
		encoding=_encodings['fs'], errors='strict'), 'wb')
	myfile.write(splits[1])
	myfile.close()
	return True

def xsplit_mem(mydat):
	if mydat[0:8] != b'XPAKPACK':
		return None
	if mydat[-8:] != b'XPAKSTOP':
		return None
	indexsize = decodeint(mydat[8:12])
	return (mydat[16:indexsize + 16], mydat[indexsize + 16:-8])

def getindex(infile):
	"""(infile) -- grabs the index segment from the infile and returns it."""
	myfile = open(_unicode_encode(infile,
		encoding=_encodings['fs'], errors='strict'), 'rb')
	myheader = myfile.read(16)
	if myheader[0:8] != b'XPAKPACK':
		myfile.close()
		return
	indexsize = decodeint(myheader[8:12])
	myindex = myfile.read(indexsize)
	myfile.close()
	return myindex

def getboth(infile):
	"""(infile) -- grabs the index and data segments from the infile.
	Returns an array [indexSegment, dataSegment]"""
	myfile = open(_unicode_encode(infile,
		encoding=_encodings['fs'], errors='strict'), 'rb')
	myheader = myfile.read(16)
	if myheader[0:8] != b'XPAKPACK':
		myfile.close()
		return
	indexsize = decodeint(myheader[8:12])
	datasize = decodeint(myheader[12:16])
	myindex = myfile.read(indexsize)
	mydata = myfile.read(datasize)
	myfile.close()
	return myindex, mydata

def listindex(myindex):
	"""Print to the terminal the filenames listed in the indexglob passed in."""
	for x in getindex_mem(myindex):
		print(x)

def getindex_mem(myindex):
	"""Returns the filenames listed in the indexglob passed in."""
	myindexlen = len(myindex)
	startpos = 0
	myret = []
	while (startpos + 8) < myindexlen:
		mytestlen = decodeint(myindex[startpos:startpos + 4])
		myret = myret + [myindex[startpos + 4:startpos + 4 + mytestlen]]
		startpos = startpos + mytestlen + 12
	return myret

def searchindex(myindex, myitem):
	"""(index, item) -- Finds the offset and length of the file 'item' in the
	datasegment via the index 'index' provided."""
	myitem = _unicode_encode(myitem,
		encoding=_encodings['repo.content'], errors='backslashreplace')
	mylen = len(myitem)
	myindexlen = len(myindex)
	startpos = 0
	while (startpos + 8) < myindexlen:
		mytestlen = decodeint(myindex[startpos:startpos + 4])
		if mytestlen == mylen:
			if myitem == myindex[startpos + 4:startpos + 4 + mytestlen]:
				#found
				datapos = decodeint(myindex[startpos + 4 + mytestlen:startpos + 8 + mytestlen])
				datalen = decodeint(myindex[startpos + 8 + mytestlen:startpos + 12 + mytestlen])
				return datapos, datalen
		startpos = startpos + mytestlen + 12

def getitem(myid, myitem):
	myindex = myid[0]
	mydata = myid[1]
	myloc = searchindex(myindex, myitem)
	if not myloc:
		return None
	return mydata[myloc[0]:myloc[0] + myloc[1]]

def xpand(myid, mydest):
	mydest = normalize_path(mydest) + os.sep
	myindex = myid[0]
	mydata = myid[1]
	myindexlen = len(myindex)
	startpos = 0
	while (startpos + 8) < myindexlen:
		namelen = decodeint(myindex[startpos:startpos + 4])
		datapos = decodeint(myindex[startpos + 4 + namelen:startpos + 8 + namelen])
		datalen = decodeint(myindex[startpos + 8 + namelen:startpos + 12 + namelen])
		myname = myindex[startpos + 4:startpos + 4 + namelen]
		myname = _unicode_decode(myname,
			encoding=_encodings['repo.content'], errors='replace')
		filename = os.path.join(mydest, myname.lstrip(os.sep))
		filename = normalize_path(filename)
		if not filename.startswith(mydest):
			# myname contains invalid ../ component(s)
			continue
		dirname = os.path.dirname(filename)
		if dirname:
			if not os.path.exists(dirname):
				os.makedirs(dirname)
		mydat = open(_unicode_encode(filename,
			encoding=_encodings['fs'], errors='strict'), 'wb')
		mydat.write(mydata[datapos:datapos + datalen])
		mydat.close()
		startpos = startpos + namelen + 12

class tbz2:
	def __init__(self, myfile):
		self.file = myfile
		self.filestat = None
		self.index = b''
		self.infosize = 0
		self.xpaksize = 0
		self.indexsize = None
		self.datasize = None
		self.indexpos = None
		self.datapos = None

	def decompose(self, datadir, cleanup=1):
		"""Alias for unpackinfo() --- Complement to recompose() but optionally
		deletes the destination directory. Extracts the xpak from the tbz2 into
		the directory provided. Raises IOError if scan() fails.
		Returns result of upackinfo()."""
		if not self.scan():
			raise IOError
		if cleanup:
			self.cleanup(datadir)
		if not os.path.exists(datadir):
			os.makedirs(datadir)
		return self.unpackinfo(datadir)
	def compose(self, datadir, cleanup=0):
		"""Alias for recompose()."""
		return self.recompose(datadir, cleanup)

	def recompose(self, datadir, cleanup=0, break_hardlinks=True):
		"""Creates an xpak segment from the datadir provided, truncates the tbz2
		to the end of regular data if an xpak segment already exists, and adds
		the new segment to the file with terminating info."""
		xpdata = xpak(datadir)
		self.recompose_mem(xpdata, break_hardlinks=break_hardlinks)
		if cleanup:
			self.cleanup(datadir)

	def recompose_mem(self, xpdata, break_hardlinks=True):
		"""
		Update the xpak segment.
		@param xpdata: A new xpak segment to be written, like that returned
			from the xpak_mem() function.
		@param break_hardlinks: If hardlinks exist, create a copy in order
			to break them. This makes it safe to use hardlinks to create
			cheap snapshots of the repository, which is useful for solving
			race conditions on binhosts as described here:
			https://crbug.com/185031
			Default is True.
		"""
		self.scan() # Don't care about condition... We'll rewrite the data anyway.

		if break_hardlinks and self.filestat and self.filestat.st_nlink > 1:
			tmp_fname = "%s.%d" % (self.file, portage.getpid())
			copyfile(self.file, tmp_fname)
			try:
				portage.util.apply_stat_permissions(self.file, self.filestat)
			except portage.exception.OperationNotPermitted:
				pass
			os.rename(tmp_fname, self.file)

		myfile = open(_unicode_encode(self.file,
			encoding=_encodings['fs'], errors='strict'), 'ab+')
		if not myfile:
			raise IOError
		myfile.seek(-self.xpaksize, 2) # 0,2 or -0,2 just mean EOF.
		myfile.truncate()
		myfile.write(xpdata + encodeint(len(xpdata)) + b'STOP')
		myfile.flush()
		myfile.close()
		return 1

	def cleanup(self, datadir):
		datadir_split = os.path.split(datadir)
		if len(datadir_split) >= 2 and len(datadir_split[1]) > 0:
			# This is potentially dangerous,
			# thus the above sanity check.
			try:
				shutil.rmtree(datadir)
			except OSError as oe:
				if oe.errno == errno.ENOENT:
					pass
				else:
					raise oe

	def scan(self):
		"""Scans the tbz2 to locate the xpak segment and setup internal values.
		This function is called by relevant functions already."""
		a = None
		try:
			mystat = os.stat(self.file)
			if self.filestat:
				changed = 0
				if mystat.st_size != self.filestat.st_size \
					or mystat.st_mtime != self.filestat.st_mtime \
					or mystat.st_ctime != self.filestat.st_ctime:
					changed = True
				if not changed:
					return 1
			self.filestat = mystat
			a = open(_unicode_encode(self.file,
				encoding=_encodings['fs'], errors='strict'), 'rb')
			a.seek(-16, 2)
			trailer = a.read()
			self.infosize = 0
			self.xpaksize = 0
			if trailer[-4:] != b'STOP':
				return 0
			if trailer[0:8] != b'XPAKSTOP':
				return 0
			self.infosize = decodeint(trailer[8:12])
			self.xpaksize = self.infosize + 8
			a.seek(-(self.xpaksize), 2)
			header = a.read(16)
			if header[0:8] != b'XPAKPACK':
				return 0
			self.indexsize = decodeint(header[8:12])
			self.datasize = decodeint(header[12:16])
			self.indexpos = a.tell()
			self.index = a.read(self.indexsize)
			self.datapos = a.tell()
			return 2
		except SystemExit:
			raise
		except:
			return 0
		finally:
			if a is not None:
				a.close()

	def filelist(self):
		"""Return an array of each file listed in the index."""
		if not self.scan():
			return None
		return getindex_mem(self.index)

	def getfile(self, myfile, mydefault=None):
		"""Finds 'myfile' in the data segment and returns it."""
		if not self.scan():
			return None
		myresult = searchindex(self.index, myfile)
		if not myresult:
			return mydefault
		a = open(_unicode_encode(self.file,
			encoding=_encodings['fs'], errors='strict'), 'rb')
		a.seek(self.datapos + myresult[0], 0)
		myreturn = a.read(myresult[1])
		a.close()
		return myreturn

	def getelements(self, myfile):
		"""A split/array representation of tbz2.getfile()"""
		mydat = self.getfile(myfile)
		if not mydat:
			return []
		return mydat.split()

	def unpackinfo(self, mydest):
		"""Unpacks all the files from the dataSegment into 'mydest'."""
		if not self.scan():
			return 0
		mydest = normalize_path(mydest) + os.sep
		a = open(_unicode_encode(self.file,
			encoding=_encodings['fs'], errors='strict'), 'rb')
		if not os.path.exists(mydest):
			os.makedirs(mydest)
		startpos = 0
		while (startpos + 8) < self.indexsize:
			namelen = decodeint(self.index[startpos:startpos + 4])
			datapos = decodeint(self.index[startpos + 4 + namelen:startpos + 8 + namelen])
			datalen = decodeint(self.index[startpos + 8 + namelen:startpos + 12 + namelen])
			myname = self.index[startpos + 4:startpos + 4 + namelen]
			myname = _unicode_decode(myname,
				encoding=_encodings['repo.content'], errors='replace')
			filename = os.path.join(mydest, myname.lstrip(os.sep))
			filename = normalize_path(filename)
			if not filename.startswith(mydest):
				# myname contains invalid ../ component(s)
				continue
			dirname = os.path.dirname(filename)
			if dirname:
				if not os.path.exists(dirname):
					os.makedirs(dirname)
			mydat = open(_unicode_encode(filename,
				encoding=_encodings['fs'], errors='strict'), 'wb')
			a.seek(self.datapos + datapos)
			mydat.write(a.read(datalen))
			mydat.close()
			startpos = startpos + namelen + 12
		a.close()
		return 1

	def get_data(self):
		"""Returns all the files from the dataSegment as a map object."""
		if not self.scan():
			return {}
		a = open(_unicode_encode(self.file,
			encoding=_encodings['fs'], errors='strict'), 'rb')
		mydata = {}
		startpos = 0
		while (startpos + 8) < self.indexsize:
			namelen = decodeint(self.index[startpos:startpos + 4])
			datapos = decodeint(self.index[startpos + 4 + namelen:startpos + 8 + namelen])
			datalen = decodeint(self.index[startpos + 8 + namelen:startpos + 12 + namelen])
			myname = self.index[startpos + 4:startpos + 4 + namelen]
			a.seek(self.datapos + datapos)
			mydata[myname] = a.read(datalen)
			startpos = startpos + namelen + 12
		a.close()
		return mydata

	def getboth(self):
		"""Returns an array [indexSegment, dataSegment]"""
		if not self.scan():
			return None

		a = open(_unicode_encode(self.file,
			encoding=_encodings['fs'], errors='strict'), 'rb')
		a.seek(self.datapos)
		mydata = a.read(self.datasize)
		a.close()

		return self.index, mydata
