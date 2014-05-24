
import errno
import logging
import tempfile
import time

try:
	from urllib.parse import urlparse
except ImportError:
	from urlparse import urlparse


import portage
from portage import os
from portage.output import green


metadata_xml_encoding = 'UTF-8'
metadata_xml_declaration = '<?xml version="1.0" encoding="%s"?>' \
	% (metadata_xml_encoding,)
metadata_doctype_name = 'pkgmetadata'
metadata_dtd_uri = 'http://www.gentoo.org/dtd/metadata.dtd'
# force refetch if the local copy creation time is older than this
metadata_dtd_ctime_interval = 60 * 60 * 24 * 7  # 7 days


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
