# -*- coding:utf-8 -*-

from __future__ import print_function

import errno
import logging
import sys
import time

# import our initialized portage instance
from repoman._portage import portage

from portage import os
from portage.output import green
from portage.package.ebuild.fetch import fetch


# Note: This URI is hardcoded in all metadata.xml files.  We can't
# change it without updating all the xml files in the tree.
metadata_dtd_uri = 'https://www.gentoo.org/dtd/metadata.dtd'
metadata_xsd_uri = 'https://www.gentoo.org/xml-schema/metadata.xsd'
# force refetch if the local copy creation time is older than this
metadata_xsd_ctime_interval = 60 * 60 * 24 * 7  # 7 days


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

		if not fetch([metadata_xsd_uri], repoman_settings, force=1, try_mirrors=0):
			logging.error(
				"failed to fetch metadata.xsd from '%s'" % metadata_xsd_uri)
			return False

		try:
			portage.util.apply_secpass_permissions(metadata_xsd,
				gid=portage.data.portage_gid, mode=0o664, mask=0o2)
		except portage.exception.PortageException:
			pass

	return True


def get_metadata_xsd(repo_settings):
	'''Locate and or fetch the metadata.xsd file

	@param repo_settings: RepoSettings instance
	@returns: path to the metadata.xsd file
	'''
	metadata_xsd = None
	paths = list(repo_settings.repo_config.eclass_db.porttrees)
	paths.reverse()
	# add the test copy
	paths.append("/usr/lib/portage/cnf/")
	for path in paths:
		path = os.path.join(path, 'metadata/xml-schema/metadata.xsd')
		if os.path.exists(path):
			metadata_xsd = path
			break
	if metadata_xsd is None:
		metadata_xsd = os.path.join(
			repo_settings.repoman_settings["DISTDIR"], 'metadata.xsd'
			)

		fetch_metadata_xsd(metadata_xsd, repo_settings.repoman_settings)
	return metadata_xsd
