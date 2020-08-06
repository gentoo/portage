# getbinpkg.py -- Portage binary-package helper functions
# Copyright 2003-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.output import colorize
from portage.cache.mappings import slot_dict_class
from portage.localization import _
import portage
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.package.ebuild.fetch import _hide_url_passwd
from _emerge.Package import _all_metadata_keys

import pickle
import sys
import socket
import time
import tempfile
import base64
import warnings

_all_errors = [NotImplementedError, ValueError, socket.error]

from html.parser import HTMLParser as html_parser_HTMLParser
from urllib.parse import unquote as urllib_parse_unquote

try:
	import ftplib
except ImportError as e:
	sys.stderr.write(colorize("BAD", "!!! CANNOT IMPORT FTPLIB: ") + str(e) + "\n")
else:
	_all_errors.extend(ftplib.all_errors)

try:
	from http.client import HTTPConnection as http_client_HTTPConnection
	from http.client import BadStatusLine as http_client_BadStatusLine
	from http.client import ResponseNotReady as http_client_ResponseNotReady
	from http.client import error as http_client_error
except ImportError as e:
	sys.stderr.write(colorize("BAD", "!!! CANNOT IMPORT HTTP.CLIENT: ") + str(e) + "\n")
else:
	_all_errors.append(http_client_error)

_all_errors = tuple(_all_errors)


def make_metadata_dict(data):

	warnings.warn("portage.getbinpkg.make_metadata_dict() is deprecated",
		DeprecationWarning, stacklevel=2)

	myid, _myglob = data

	mydict = {}
	for k_bytes in portage.xpak.getindex_mem(myid):
		k = _unicode_decode(k_bytes,
			encoding=_encodings['repo.content'], errors='replace')
		if k not in _all_metadata_keys and k != "CATEGORY":
			continue
		v = _unicode_decode(portage.xpak.getitem(data, k_bytes),
			encoding=_encodings['repo.content'], errors='replace')
		mydict[k] = v

	return mydict

class ParseLinks(html_parser_HTMLParser):
	"""Parser class that overrides HTMLParser to grab all anchors from an html
	page and provide suffix and prefix limitors"""
	def __init__(self):

		warnings.warn("portage.getbinpkg.ParseLinks is deprecated",
			DeprecationWarning, stacklevel=2)

		self.PL_anchors = []
		html_parser_HTMLParser.__init__(self)

	def get_anchors(self):
		return self.PL_anchors

	def get_anchors_by_prefix(self, prefix):
		newlist = []
		for x in self.PL_anchors:
			if x.startswith(prefix):
				if x not in newlist:
					newlist.append(x[:])
		return newlist

	def get_anchors_by_suffix(self, suffix):
		newlist = []
		for x in self.PL_anchors:
			if x.endswith(suffix):
				if x not in newlist:
					newlist.append(x[:])
		return newlist

	def	handle_endtag(self, tag):
		pass

	def	handle_starttag(self, tag, attrs):
		if tag == "a":
			for x in attrs:
				if x[0] == 'href':
					if x[1] not in self.PL_anchors:
						self.PL_anchors.append(urllib_parse_unquote(x[1]))


def create_conn(baseurl, conn=None):
	"""Takes a protocol://site:port/address url, and an
	optional connection. If connection is already active, it is passed on.
	baseurl is reduced to address and is returned in tuple (conn,address)"""

	warnings.warn("portage.getbinpkg.create_conn() is deprecated",
		DeprecationWarning, stacklevel=2)

	parts = baseurl.split("://", 1)
	if len(parts) != 2:
		raise ValueError(_("Provided URI does not "
			"contain protocol identifier. '%s'") % baseurl)
	protocol, url_parts = parts
	del parts

	url_parts = url_parts.split("/")
	host = url_parts[0]
	if len(url_parts) < 2:
		address = "/"
	else:
		address = "/"+"/".join(url_parts[1:])
	del url_parts

	userpass_host = host.split("@", 1)
	if len(userpass_host) == 1:
		host = userpass_host[0]
		userpass = ["anonymous"]
	else:
		host = userpass_host[1]
		userpass = userpass_host[0].split(":")
	del userpass_host

	if len(userpass) > 2:
		raise ValueError(_("Unable to interpret username/password provided."))
	elif len(userpass) == 2:
		username = userpass[0]
		password = userpass[1]
	elif len(userpass) == 1:
		username = userpass[0]
		password = None
	del userpass

	http_headers = {}
	http_params = {}
	if username and password:
		try:
			encodebytes = base64.encodebytes
		except AttributeError:
			# Python 2
			encodebytes = base64.encodestring
		http_headers = {
			b"Authorization": "Basic %s" % \
			encodebytes(_unicode_encode("%s:%s" % (username, password))).replace(
			    b"\012",
			    b""
			  ),
		}

	if not conn:
		if protocol == "https":
			# Use local import since https typically isn't needed, and
			# this way we can usually avoid triggering the global scope
			# http.client ImportError handler (like during stage1 -> stage2
			# builds where USE=ssl is disabled for python).
			try:
				from http.client import HTTPSConnection as http_client_HTTPSConnection
			except ImportError:
				raise NotImplementedError(
					_("python must have ssl enabled for https support"))
			conn = http_client_HTTPSConnection(host)
		elif protocol == "http":
			conn = http_client_HTTPConnection(host)
		elif protocol == "ftp":
			passive = 1
			if host[-1] == "*":
				passive = 0
				host = host[:-1]
			conn = ftplib.FTP(host)
			if password:
				conn.login(username, password)
			else:
				sys.stderr.write(colorize("WARN",
					_(" * No password provided for username")) + " '%s'" % \
					(username,) + "\n\n")
				conn.login(username)
			conn.set_pasv(passive)
			conn.set_debuglevel(0)
		elif protocol == "sftp":
			try:
				import paramiko
			except ImportError:
				raise NotImplementedError(
					_("paramiko must be installed for sftp support"))
			t = paramiko.Transport(host)
			t.connect(username=username, password=password)
			conn = paramiko.SFTPClient.from_transport(t)
		else:
			raise NotImplementedError(_("%s is not a supported protocol.") % protocol)

	return (conn, protocol, address, http_params, http_headers)

def make_ftp_request(conn, address, rest=None, dest=None):
	"""Uses the |conn| object to request the data
	from address and issuing a rest if it is passed."""

	warnings.warn("portage.getbinpkg.make_ftp_request() is deprecated",
		DeprecationWarning, stacklevel=2)

	try:

		if dest:
			fstart_pos = dest.tell()

		conn.voidcmd("TYPE I")
		fsize = conn.size(address)

		if (rest != None) and (rest < 0):
			rest = fsize+int(rest)
		if rest < 0:
			rest = 0

		if rest != None:
			mysocket = conn.transfercmd("RETR %s" % str(address), rest)
		else:
			mysocket = conn.transfercmd("RETR %s" % str(address))

		mydata = ""
		while 1:
			somedata = mysocket.recv(8192)
			if somedata:
				if dest:
					dest.write(somedata)
				else:
					mydata = mydata + somedata
			else:
				break

		if dest:
			data_size = fstart_pos - dest.tell()
		else:
			data_size = len(mydata)

		mysocket.close()
		conn.voidresp()
		conn.voidcmd("TYPE A")

		return mydata, (fsize != data_size), ""

	except ValueError as e:
		return None, int(str(e)[:4]), str(e)


def make_http_request(conn, address, _params={}, headers={}, dest=None):
	"""Uses the |conn| object to request
	the data from address, performing Location forwarding and using the
	optional params and headers."""

	warnings.warn("portage.getbinpkg.make_http_request() is deprecated",
		DeprecationWarning, stacklevel=2)

	rc = 0
	response = None
	while (rc == 0) or (rc == 301) or (rc == 302):
		try:
			if rc != 0:
				conn = create_conn(address)[0]
			conn.request("GET", address, body=None, headers=headers)
		except SystemExit as e:
			raise
		except Exception as e:
			return None, None, "Server request failed: %s" % str(e)
		response = conn.getresponse()
		rc = response.status

		# 301 means that the page address is wrong.
		if ((rc == 301) or (rc == 302)):
			ignored_data = response.read()
			del ignored_data
			for x in str(response.msg).split("\n"):
				parts = x.split(": ", 1)
				if parts[0] == "Location":
					if rc == 301:
						sys.stderr.write(colorize("BAD",
							_("Location has moved: ")) + str(parts[1]) + "\n")
					if rc == 302:
						sys.stderr.write(colorize("BAD",
							_("Location has temporarily moved: ")) + \
							str(parts[1]) + "\n")
					address = parts[1]
					break

	if (rc != 200) and (rc != 206):
		return None, rc, "Server did not respond successfully (%s: %s)" % (str(response.status), str(response.reason))

	if dest:
		dest.write(response.read())
		return "", 0, ""

	return response.read(), 0, ""


def match_in_array(array, prefix="", suffix="", match_both=1, allow_overlap=0):

	warnings.warn("portage.getbinpkg.match_in_array() is deprecated",
		DeprecationWarning, stacklevel=2)

	myarray = []

	if not (prefix and suffix):
		match_both = 0

	for x in array:
		add_p = 0
		if prefix and (len(x) >= len(prefix)) and (x[:len(prefix)] == prefix):
			add_p = 1

		if match_both:
			if prefix and not add_p: # Require both, but don't have first one.
				continue
		else:
			if add_p:     # Only need one, and we have it.
				myarray.append(x[:])
				continue

		if not allow_overlap: # Not allow to overlap prefix and suffix
			if len(x) >= (len(prefix)+len(suffix)):
				pass
			else:
				continue          # Too short to match.
		else:
			pass                      # Do whatever... We're overlapping.

		if suffix and (len(x) >= len(suffix)) and (x[-len(suffix):] == suffix):
			myarray.append(x)   # It matches
		else:
			continue            # Doesn't match.

	return myarray


def dir_get_list(baseurl, conn=None):
	"""Takes a base url to connect to and read from.
	URI should be in the form <proto>://<site>[:port]<path>
	Connection is used for persistent connection instances."""

	warnings.warn("portage.getbinpkg.dir_get_list() is deprecated",
		DeprecationWarning, stacklevel=2)

	if not conn:
		keepconnection = 0
	else:
		keepconnection = 1

	conn, protocol, address, params, headers = create_conn(baseurl, conn)

	listing = None
	if protocol in ["http","https"]:
		if not address.endswith("/"):
			# http servers can return a 400 error here
			# if the address doesn't end with a slash.
			address += "/"
		page, rc, msg = make_http_request(conn, address, params, headers)

		if page:
			parser = ParseLinks()
			parser.feed(_unicode_decode(page))
			del page
			listing = parser.get_anchors()
		else:
			import portage.exception
			raise portage.exception.PortageException(
				_("Unable to get listing: %s %s") % (rc,msg))
	elif protocol in ["ftp"]:
		if address[-1] == '/':
			olddir = conn.pwd()
			conn.cwd(address)
			listing = conn.nlst()
			conn.cwd(olddir)
			del olddir
		else:
			listing = conn.nlst(address)
	elif protocol == "sftp":
		listing = conn.listdir(address)
	else:
		raise TypeError(_("Unknown protocol. '%s'") % protocol)

	if not keepconnection:
		conn.close()

	return listing

def file_get_metadata(baseurl, conn=None, chunk_size=3000):
	"""Takes a base url to connect to and read from.
	URI should be in the form <proto>://<site>[:port]<path>
	Connection is used for persistent connection instances."""

	warnings.warn("portage.getbinpkg.file_get_metadata() is deprecated",
		DeprecationWarning, stacklevel=2)

	if not conn:
		keepconnection = 0
	else:
		keepconnection = 1

	conn, protocol, address, params, headers = create_conn(baseurl, conn)

	if protocol in ["http","https"]:
		headers["Range"] = "bytes=-%s" % str(chunk_size)
		data, _x, _x = make_http_request(conn, address, params, headers)
	elif protocol in ["ftp"]:
		data, _x, _x = make_ftp_request(conn, address, -chunk_size)
	elif protocol == "sftp":
		f = conn.open(address)
		try:
			f.seek(-chunk_size, 2)
			data = f.read()
		finally:
			f.close()
	else:
		raise TypeError(_("Unknown protocol. '%s'") % protocol)

	if data:
		xpaksize = portage.xpak.decodeint(data[-8:-4])
		if (xpaksize + 8) > chunk_size:
			myid = file_get_metadata(baseurl, conn, xpaksize + 8)
			if not keepconnection:
				conn.close()
			return myid
		xpak_data = data[len(data) - (xpaksize + 8):-8]
		del data

		myid = portage.xpak.xsplit_mem(xpak_data)
		if not myid:
			myid = None, None
		del xpak_data
	else:
		myid = None, None

	if not keepconnection:
		conn.close()

	return myid


def file_get(baseurl=None, dest=None, conn=None, fcmd=None, filename=None,
	fcmd_vars=None):
	"""Takes a base url to connect to and read from.
	URI should be in the form <proto>://[user[:pass]@]<site>[:port]<path>"""

	if not fcmd:

		warnings.warn("Use of portage.getbinpkg.file_get() without the fcmd "
			"parameter is deprecated", DeprecationWarning, stacklevel=2)

		return file_get_lib(baseurl, dest, conn)

	variables = {}

	if fcmd_vars is not None:
		variables.update(fcmd_vars)

	if "DISTDIR" not in variables:
		if dest is None:
			raise portage.exception.MissingParameter(
				_("%s is missing required '%s' key") %
				("fcmd_vars", "DISTDIR"))
		variables["DISTDIR"] = dest

	if "URI" not in variables:
		if baseurl is None:
			raise portage.exception.MissingParameter(
				_("%s is missing required '%s' key") %
				("fcmd_vars", "URI"))
		variables["URI"] = baseurl

	if "FILE" not in variables:
		if filename is None:
			filename = os.path.basename(variables["URI"])
		variables["FILE"] = filename

	from portage.util import varexpand
	from portage.process import spawn
	myfetch = portage.util.shlex_split(fcmd)
	myfetch = [varexpand(x, mydict=variables) for x in myfetch]
	fd_pipes = {
		0: portage._get_stdin().fileno(),
		1: sys.__stdout__.fileno(),
		2: sys.__stdout__.fileno()
	}
	sys.__stdout__.flush()
	sys.__stderr__.flush()
	retval = spawn(myfetch, env=os.environ.copy(), fd_pipes=fd_pipes)
	if retval != os.EX_OK:
		sys.stderr.write(_("Fetcher exited with a failure condition.\n"))
		return 0
	return 1

def file_get_lib(baseurl, dest, conn=None):
	"""Takes a base url to connect to and read from.
	URI should be in the form <proto>://<site>[:port]<path>
	Connection is used for persistent connection instances."""

	warnings.warn("portage.getbinpkg.file_get_lib() is deprecated",
		DeprecationWarning, stacklevel=2)

	if not conn:
		keepconnection = 0
	else:
		keepconnection = 1

	conn, protocol, address, params, headers = create_conn(baseurl, conn)

	sys.stderr.write("Fetching '" + str(os.path.basename(address)) + "'\n")
	if protocol in ["http", "https"]:
		data, rc, _msg = make_http_request(conn, address, params, headers, dest=dest)
	elif protocol in ["ftp"]:
		data, rc, _msg = make_ftp_request(conn, address, dest=dest)
	elif protocol == "sftp":
		rc = 0
		try:
			f = conn.open(address)
		except SystemExit:
			raise
		except Exception:
			rc = 1
		else:
			try:
				if dest:
					bufsize = 8192
					while True:
						data = f.read(bufsize)
						if not data:
							break
						dest.write(data)
			finally:
				f.close()
	else:
		raise TypeError(_("Unknown protocol. '%s'") % protocol)

	if not keepconnection:
		conn.close()

	return rc


def dir_get_metadata(baseurl, conn=None, chunk_size=3000, verbose=1, usingcache=1, makepickle=None):

	warnings.warn("portage.getbinpkg.dir_get_metadata() is deprecated",
		DeprecationWarning, stacklevel=2)

	if not conn:
		keepconnection = 0
	else:
		keepconnection = 1

	cache_path = "/var/cache/edb"
	metadatafilename = os.path.join(cache_path, 'remote_metadata.pickle')

	if makepickle is None:
		makepickle = "/var/cache/edb/metadata.idx.most_recent"

	try:
		conn = create_conn(baseurl, conn)[0]
	except _all_errors as e:
		# ftplib.FTP(host) can raise errors like this:
		#   socket.error: (111, 'Connection refused')
		sys.stderr.write("!!! %s\n" % (e,))
		return {}

	out = sys.stdout
	try:
		metadatafile = open(_unicode_encode(metadatafilename,
			encoding=_encodings['fs'], errors='strict'), 'rb')
		mypickle = pickle.Unpickler(metadatafile)
		try:
			mypickle.find_global = None
		except AttributeError:
			# TODO: If py3k, override Unpickler.find_class().
			pass
		metadata = mypickle.load()
		out.write(_("Loaded metadata pickle.\n"))
		out.flush()
		metadatafile.close()
	except (SystemExit, KeyboardInterrupt):
		raise
	except Exception:
		metadata = {}
	if baseurl not in metadata:
		metadata[baseurl] = {}
	if "indexname" not in metadata[baseurl]:
		metadata[baseurl]["indexname"] = ""
	if "timestamp" not in metadata[baseurl]:
		metadata[baseurl]["timestamp"] = 0
	if "unmodified" not in metadata[baseurl]:
		metadata[baseurl]["unmodified"] = 0
	if "data" not in metadata[baseurl]:
		metadata[baseurl]["data"] = {}

	if not os.access(cache_path, os.W_OK):
		sys.stderr.write(_("!!! Unable to write binary metadata to disk!\n"))
		sys.stderr.write(_("!!! Permission denied: '%s'\n") % cache_path)
		return metadata[baseurl]["data"]

	import portage.exception
	try:
		filelist = dir_get_list(baseurl, conn)
	except portage.exception.PortageException as e:
		sys.stderr.write(_("!!! Error connecting to '%s'.\n") %
			_hide_url_passwd(baseurl))
		sys.stderr.write("!!! %s\n" % str(e))
		del e
		return metadata[baseurl]["data"]
	tbz2list = match_in_array(filelist, suffix=".tbz2")
	metalist = match_in_array(filelist, prefix="metadata.idx")
	del filelist

	# Determine if our metadata file is current.
	metalist.sort()
	metalist.reverse() # makes the order new-to-old.
	for mfile in metalist:
		if usingcache and \
		   ((metadata[baseurl]["indexname"] != mfile) or \
			  (metadata[baseurl]["timestamp"] < int(time.time() - (60 * 60 * 24)))):
			# Try to download new cache until we succeed on one.
			data = ""
			for trynum in [1, 2, 3]:
				mytempfile = tempfile.TemporaryFile()
				try:
					file_get(baseurl + "/" + mfile, mytempfile, conn)
					if mytempfile.tell() > len(data):
						mytempfile.seek(0)
						data = mytempfile.read()
				except ValueError as e:
					sys.stderr.write("--- %s\n" % str(e))
					if trynum < 3:
						sys.stderr.write(_("Retrying...\n"))
					sys.stderr.flush()
					mytempfile.close()
					continue
				if match_in_array([mfile], suffix=".gz"):
					out.write("gzip'd\n")
					out.flush()
					try:
						import gzip
						mytempfile.seek(0)
						gzindex = gzip.GzipFile(mfile[:-3], 'rb', 9, mytempfile)
						data = gzindex.read()
					except SystemExit as e:
						raise
					except Exception as e:
						mytempfile.close()
						sys.stderr.write(_("!!! Failed to use gzip: ") + str(e) + "\n")
						sys.stderr.flush()
					mytempfile.close()
				try:
					metadata[baseurl]["data"] = pickle.loads(data)
					del data
					metadata[baseurl]["indexname"] = mfile
					metadata[baseurl]["timestamp"] = int(time.time())
					metadata[baseurl]["modified"]  = 0 # It's not, right after download.
					out.write(_("Pickle loaded.\n"))
					out.flush()
					break
				except SystemExit as e:
					raise
				except Exception as e:
					sys.stderr.write(_("!!! Failed to read data from index: ") + str(mfile) + "\n")
					sys.stderr.write("!!! %s" % str(e))
					sys.stderr.flush()
			try:
				metadatafile = open(_unicode_encode(metadatafilename,
					encoding=_encodings['fs'], errors='strict'), 'wb')
				pickle.dump(metadata, metadatafile, protocol=2)
				metadatafile.close()
			except SystemExit as e:
				raise
			except Exception as e:
				sys.stderr.write(_("!!! Failed to write binary metadata to disk!\n"))
				sys.stderr.write("!!! %s\n" % str(e))
				sys.stderr.flush()
			break
	# We may have metadata... now we run through the tbz2 list and check.

	class CacheStats:
		from time import time
		def __init__(self, out):
			self.misses = 0
			self.hits = 0
			self.last_update = 0
			self.out = out
			self.min_display_latency = 0.2
		def update(self):
			cur_time = self.time()
			if cur_time - self.last_update >= self.min_display_latency:
				self.last_update = cur_time
				self.display()
		def display(self):
			self.out.write("\r"+colorize("WARN",
				_("cache miss: '") + str(self.misses) + "'") + \
				" --- " + colorize("GOOD", _("cache hit: '") + str(self.hits) + "'"))
			self.out.flush()

	cache_stats = CacheStats(out)
	have_tty = os.environ.get('TERM') != 'dumb' and out.isatty()
	if have_tty:
		cache_stats.display()
	binpkg_filenames = set()
	for x in tbz2list:
		x = os.path.basename(x)
		binpkg_filenames.add(x)
		if x not in metadata[baseurl]["data"]:
			cache_stats.misses += 1
			if have_tty:
				cache_stats.update()
			metadata[baseurl]["modified"] = 1
			myid = None
			for _x in range(3):
				try:
					myid = file_get_metadata(
						"/".join((baseurl.rstrip("/"), x.lstrip("/"))),
						conn, chunk_size)
					break
				except http_client_BadStatusLine:
					# Sometimes this error is thrown from conn.getresponse() in
					# make_http_request().  The docstring for this error in
					# httplib.py says "Presumably, the server closed the
					# connection before sending a valid response".
					conn = create_conn(baseurl)[0]
				except http_client_ResponseNotReady:
					# With some http servers this error is known to be thrown
					# from conn.getresponse() in make_http_request() when the
					# remote file does not have appropriate read permissions.
					# Maybe it's possible to recover from this exception in
					# cases though, so retry.
					conn = create_conn(baseurl)[0]

			if myid and myid[0]:
				metadata[baseurl]["data"][x] = make_metadata_dict(myid)
			elif verbose:
				sys.stderr.write(colorize("BAD",
					_("!!! Failed to retrieve metadata on: ")) + str(x) + "\n")
				sys.stderr.flush()
		else:
			cache_stats.hits += 1
			if have_tty:
				cache_stats.update()
	cache_stats.display()
	# Cleanse stale cache for files that don't exist on the server anymore.
	stale_cache = set(metadata[baseurl]["data"]).difference(binpkg_filenames)
	if stale_cache:
		for x in stale_cache:
			del metadata[baseurl]["data"][x]
		metadata[baseurl]["modified"] = 1
	del stale_cache
	del binpkg_filenames
	out.write("\n")
	out.flush()

	try:
		if "modified" in metadata[baseurl] and metadata[baseurl]["modified"]:
			metadata[baseurl]["timestamp"] = int(time.time())
			metadatafile = open(_unicode_encode(metadatafilename,
				encoding=_encodings['fs'], errors='strict'), 'wb')
			pickle.dump(metadata, metadatafile, protocol=2)
			metadatafile.close()
		if makepickle:
			metadatafile = open(_unicode_encode(makepickle,
				encoding=_encodings['fs'], errors='strict'), 'wb')
			pickle.dump(metadata[baseurl]["data"], metadatafile, protocol=2)
			metadatafile.close()
	except SystemExit as e:
		raise
	except Exception as e:
		sys.stderr.write(_("!!! Failed to write binary metadata to disk!\n"))
		sys.stderr.write("!!! "+str(e)+"\n")
		sys.stderr.flush()

	if not keepconnection:
		conn.close()

	return metadata[baseurl]["data"]

def _cmp_cpv(d1, d2):
	cpv1 = d1["CPV"]
	cpv2 = d2["CPV"]
	if cpv1 > cpv2:
		return 1
	if cpv1 == cpv2:
		return 0
	return -1

class PackageIndex:

	def __init__(self,
		allowed_pkg_keys=None,
		default_header_data=None,
		default_pkg_data=None,
		inherited_keys=None,
		translated_keys=None):

		self._pkg_slot_dict = None
		if allowed_pkg_keys is not None:
			self._pkg_slot_dict = slot_dict_class(allowed_pkg_keys)

		self._default_header_data = default_header_data
		self._default_pkg_data = default_pkg_data
		self._inherited_keys = inherited_keys
		self._write_translation_map = {}
		self._read_translation_map = {}
		if translated_keys:
			self._write_translation_map.update(translated_keys)
			self._read_translation_map.update(((y, x) for (x, y) in translated_keys))
		self.header = {}
		if self._default_header_data:
			self.header.update(self._default_header_data)
		self.packages = []
		self.modified = True

	def _readpkgindex(self, pkgfile, pkg_entry=True):

		allowed_keys = None
		if self._pkg_slot_dict is None or not pkg_entry:
			d = {}
		else:
			d = self._pkg_slot_dict()
			allowed_keys = d.allowed_keys

		for line in pkgfile:
			line = line.rstrip("\n")
			if not line:
				break
			line = line.split(":", 1)
			if not len(line) == 2:
				continue
			k, v = line
			if v:
				v = v[1:]
			k = self._read_translation_map.get(k, k)
			if allowed_keys is not None and \
				k not in allowed_keys:
				continue
			d[k] = v
		return d

	def _writepkgindex(self, pkgfile, items):
		for k, v in items:
			pkgfile.write("%s: %s\n" % \
				(self._write_translation_map.get(k, k), v))
		pkgfile.write("\n")

	def read(self, pkgfile):
		self.readHeader(pkgfile)
		self.readBody(pkgfile)

	def readHeader(self, pkgfile):
		self.header.update(self._readpkgindex(pkgfile, pkg_entry=False))

	def readBody(self, pkgfile):
		while True:
			d = self._readpkgindex(pkgfile)
			if not d:
				break
			mycpv = d.get("CPV")
			if not mycpv:
				continue
			if self._default_pkg_data:
				for k, v in self._default_pkg_data.items():
					d.setdefault(k, v)
			if self._inherited_keys:
				for k in self._inherited_keys:
					v = self.header.get(k)
					if v is not None:
						d.setdefault(k, v)
			self.packages.append(d)

	def write(self, pkgfile):
		if self.modified:
			self.header["TIMESTAMP"] = str(int(time.time()))
			self.header["PACKAGES"] = str(len(self.packages))
		keys = list(self.header)
		keys.sort()
		self._writepkgindex(pkgfile, [(k, self.header[k]) \
			for k in keys if self.header[k]])
		for metadata in sorted(self.packages,
			key=portage.util.cmp_sort_key(_cmp_cpv)):
			metadata = metadata.copy()
			if self._inherited_keys:
				for k in self._inherited_keys:
					v = self.header.get(k)
					if v is not None and v == metadata.get(k):
						del metadata[k]
			if self._default_pkg_data:
				for k, v in self._default_pkg_data.items():
					if metadata.get(k) == v:
						metadata.pop(k, None)
			keys = list(metadata)
			keys.sort()
			self._writepkgindex(pkgfile,
				[(k, metadata[k]) for k in keys if metadata[k]])
