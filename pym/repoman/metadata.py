
import errno
import logging
import sys
import tempfile
import time

try:
	from urllib.parse import urlparse
except ImportError:
	from urlparse import urlparse


# import our initialized portage instance
from repoman._portage import portage

from portage import exception
from portage import os
from portage.output import green

if sys.hexversion >= 0x3000000:
	basestring = str

if sys.hexversion >= 0x3000000:
	basestring = str

metadata_xml_encoding = 'UTF-8'
metadata_xml_declaration = '<?xml version="1.0" encoding="%s"?>' \
	% (metadata_xml_encoding,)
metadata_doctype_name = 'pkgmetadata'
metadata_dtd_uri = 'http://www.gentoo.org/dtd/metadata.dtd'
# force refetch if the local copy creation time is older than this
metadata_dtd_ctime_interval = 60 * 60 * 24 * 7  # 7 days


def parse_metadata_use(xml_tree):
	"""
	Records are wrapped in XML as per GLEP 56
	returns a dict with keys constisting of USE flag names and values
	containing their respective descriptions
	"""
	uselist = {}

	usetags = xml_tree.findall("use")
	if not usetags:
		return uselist

	# It's possible to have multiple 'use' elements.
	for usetag in usetags:
		flags = usetag.findall("flag")
		if not flags:
			# DTD allows use elements containing no flag elements.
			continue

		for flag in flags:
			pkg_flag = flag.get("name")
			if pkg_flag is None:
				raise exception.ParseError("missing 'name' attribute for 'flag' tag")
			flag_restrict = flag.get("restrict")

			# emulate the Element.itertext() method from python-2.7
			inner_text = []
			stack = []
			stack.append(flag)
			while stack:
				obj = stack.pop()
				if isinstance(obj, basestring):
					inner_text.append(obj)
					continue
				if isinstance(obj.text, basestring):
					inner_text.append(obj.text)
				if isinstance(obj.tail, basestring):
					stack.append(obj.tail)
				stack.extend(reversed(obj))

			if pkg_flag not in uselist:
				uselist[pkg_flag] = {}

			# (flag_restrict can be None)
			uselist[pkg_flag][flag_restrict] = " ".join("".join(inner_text).split())

	return uselist


def fetch_metadata_dtd(metadata_dtd, repoman_settings):
	"""
	Fetch metadata.dtd if it doesn't exist or the ctime is older than
	metadata_dtd_ctime_interval.
	@rtype: bool
	@return: True if successful, otherwise False
	"""

	must_fetch = True
	metadata_dtd_st = None
	current_time = int(time.time())
	try:
		metadata_dtd_st = os.stat(metadata_dtd)
	except EnvironmentError as e:
		if e.errno not in (errno.ENOENT, errno.ESTALE):
			raise
		del e
	else:
		# Trigger fetch if metadata.dtd mtime is old or clock is wrong.
		if abs(current_time - metadata_dtd_st.st_ctime) \
			< metadata_dtd_ctime_interval:
			must_fetch = False

	if must_fetch:
		print()
		print(
			"%s the local copy of metadata.dtd "
			"needs to be refetched, doing that now" % green("***"))
		print()
		parsed_url = urlparse(metadata_dtd_uri)
		setting = 'FETCHCOMMAND_' + parsed_url.scheme.upper()
		fcmd = repoman_settings.get(setting)
		if not fcmd:
			fcmd = repoman_settings.get('FETCHCOMMAND')
			if not fcmd:
				logging.error("FETCHCOMMAND is unset")
				return False

		destdir = repoman_settings["DISTDIR"]
		fd, metadata_dtd_tmp = tempfile.mkstemp(
			prefix='metadata.dtd.', dir=destdir)
		os.close(fd)

		try:
			if not portage.getbinpkg.file_get(
				metadata_dtd_uri, destdir, fcmd=fcmd,
				filename=os.path.basename(metadata_dtd_tmp)):
				logging.error(
					"failed to fetch metadata.dtd from '%s'" % metadata_dtd_uri)
				return False

			try:
				portage.util.apply_secpass_permissions(
					metadata_dtd_tmp,
					gid=portage.data.portage_gid, mode=0o664, mask=0o2)
			except portage.exception.PortageException:
				pass

			os.rename(metadata_dtd_tmp, metadata_dtd)
		finally:
			try:
				os.unlink(metadata_dtd_tmp)
			except OSError:
				pass

	return True
