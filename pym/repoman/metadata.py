# -*- coding:utf-8 -*-

from __future__ import print_function, unicode_literals

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
from portage import shutil
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
metadata_xsd_uri = 'http://www.gentoo.org/xml-schema/metadata.xsd'
# force refetch if the local copy creation time is older than this
metadata_xsd_ctime_interval = 60 * 60 * 24 * 7  # 7 days


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


def fetch_metadata_xsd(metadata_xsd, repoman_settings):
	"""
	Fetch metadata.xsd if it doesn't exist or the ctime is older than
	metadata_xsd_ctime_interval.
	@rtype: bool
	@return: True if successful, otherwise False
	"""

	must_fetch = True
	metadata_xsd_st = None
	current_time = int(time.time())
	try:
		metadata_xsd_st = os.stat(metadata_xsd)
	except EnvironmentError as e:
		if e.errno not in (errno.ENOENT, errno.ESTALE):
			raise
		del e
	else:
		# Trigger fetch if metadata.xsd mtime is old or clock is wrong.
		if abs(current_time - metadata_xsd_st.st_ctime) \
			< metadata_xsd_ctime_interval:
			must_fetch = False

	if must_fetch:
		print()
		print(
			"%s the local copy of metadata.xsd "
			"needs to be refetched, doing that now" % green("***"))
		print()
		parsed_url = urlparse(metadata_xsd_uri)
		setting = 'FETCHCOMMAND_' + parsed_url.scheme.upper()
		fcmd = repoman_settings.get(setting)
		if not fcmd:
			fcmd = repoman_settings.get('FETCHCOMMAND')
			if not fcmd:
				logging.error("FETCHCOMMAND is unset")
				return False

		destdir = repoman_settings["DISTDIR"]
		fd, metadata_xsd_tmp = tempfile.mkstemp(
			prefix='metadata.xsd.', dir=destdir)
		os.close(fd)

		try:
			if not portage.getbinpkg.file_get(
				metadata_xsd_uri, destdir, fcmd=fcmd,
				filename=os.path.basename(metadata_xsd_tmp)):
				logging.error(
					"failed to fetch metadata.xsd from '%s'" % metadata_xsd_uri)
				return False

			try:
				portage.util.apply_secpass_permissions(
					metadata_xsd_tmp,
					gid=portage.data.portage_gid, mode=0o664, mask=0o2)
			except portage.exception.PortageException:
				pass

			shutil.move(metadata_xsd_tmp, metadata_xsd)
		finally:
			try:
				os.unlink(metadata_xsd_tmp)
			except OSError:
				pass

	return True
