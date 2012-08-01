# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys
from datetime import datetime
from time import mktime
from email.utils import formatdate, parsedate

try:
	from urllib.request import urlopen as _urlopen
	import urllib.parse as urllib_parse
	import urllib.request as urllib_request
	from urllib.parse import splituser as urllib_parse_splituser
except ImportError:
	from urllib import urlopen as _urlopen
	import urlparse as urllib_parse
	import urllib2 as urllib_request
	from urllib import splituser as urllib_parse_splituser

if sys.hexversion >= 0x3000000:
	long = int

# to account for the difference between TIMESTAMP of the index' contents
#  and the file-'mtime'
TIMESTAMP_TOLERANCE=5

def urlopen(url, if_modified_since=None):
	parse_result = urllib_parse.urlparse(url)
	try:
		if parse_result.scheme not in ("http", "https"):
			return _urlopen(url)
		request = urllib_request.Request(url)
		request.add_header('User-Agent', 'Gentoo Portage')
		if if_modified_since:
			request.add_header('If-Modified-Since', _timestamp_to_http(if_modified_since))
		opener = urllib_request.build_opener()
		hdl = opener.open(request)
		if hdl.headers.get('last-modified', ''):
			try:
				add_header = hdl.headers.add_header
			except AttributeError:
				# Python 2
				add_header = hdl.headers.addheader
			add_header('timestamp', _http_to_timestamp(hdl.headers.get('last-modified')))
		return hdl
	except SystemExit:
		raise
	except Exception as e:
		if hasattr(e, 'code') and e.code == 304: # HTTPError 304: not modified
			raise
		if sys.hexversion < 0x3000000:
			raise
		if parse_result.scheme not in ("http", "https") or \
			not parse_result.username:
			raise

	return _new_urlopen(url)

def _new_urlopen(url):
	# This is experimental code for bug #413983.
	parse_result = urllib_parse.urlparse(url)
	netloc = urllib_parse_splituser(parse_result.netloc)[1]
	url = urllib_parse.urlunparse((parse_result.scheme, netloc, parse_result.path, parse_result.params, parse_result.query, parse_result.fragment))
	password_manager = urllib_request.HTTPPasswordMgrWithDefaultRealm()
	if parse_result.username is not None:
		password_manager.add_password(None, url, parse_result.username, parse_result.password)
	auth_handler = urllib_request.HTTPBasicAuthHandler(password_manager)
	opener = urllib_request.build_opener(auth_handler)
	return opener.open(url)

def _timestamp_to_http(timestamp):
	dt = datetime.fromtimestamp(float(long(timestamp)+TIMESTAMP_TOLERANCE))
	stamp = mktime(dt.timetuple())
	return formatdate(timeval=stamp, localtime=False, usegmt=True)

def _http_to_timestamp(http_datetime_string):
	tuple = parsedate(http_datetime_string)
	timestamp = mktime(tuple)
	return str(long(timestamp))
