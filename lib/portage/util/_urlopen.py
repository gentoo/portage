# Copyright 2012-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import io
from datetime import datetime
from time import mktime
from email.utils import formatdate, parsedate
from urllib.request import urlopen as _urlopen
import urllib.parse as urllib_parse
import urllib.request as urllib_request


# to account for the difference between TIMESTAMP of the index' contents
#  and the file-'mtime'
TIMESTAMP_TOLERANCE = 5


def have_pep_476():
	"""
	Test whether ssl certificate verification is enabled by default for
	stdlib http clients (PEP 476).

	@returns: bool, True if ssl certificate verification is enabled by
		default
	"""
	return hasattr(__import__('ssl'), '_create_unverified_context')


def urlopen(url, if_modified_since=None, proxies=None):
	parse_result = urllib_parse.urlparse(url)
	if parse_result.scheme not in ("http", "https"):
		return _urlopen(url)

	netloc = parse_result.netloc.rpartition('@')[-1]
	url = urllib_parse.urlunparse((parse_result.scheme, netloc, parse_result.path, parse_result.params, parse_result.query, parse_result.fragment))
	password_manager = urllib_request.HTTPPasswordMgrWithDefaultRealm()
	request = urllib_request.Request(url)
	request.add_header('User-Agent', 'Gentoo Portage')
	if if_modified_since:
		request.add_header('If-Modified-Since', _timestamp_to_http(if_modified_since))
	if parse_result.username is not None:
		password_manager.add_password(None, url, parse_result.username, parse_result.password)

	handlers = [CompressedResponseProcessor(password_manager)]
	if proxies:
		handlers.append(urllib_request.ProxyHandler(proxies))
	opener = urllib_request.build_opener(*handlers)

	hdl = opener.open(request)
	if hdl.headers.get('last-modified', ''):
		try:
			add_header = hdl.headers.add_header
		except AttributeError:
			# Python 2
			add_header = hdl.headers.addheader
		add_header('timestamp', _http_to_timestamp(hdl.headers.get('last-modified')))
	return hdl

def _timestamp_to_http(timestamp):
	dt = datetime.fromtimestamp(float(int(timestamp)+TIMESTAMP_TOLERANCE))
	stamp = mktime(dt.timetuple())
	return formatdate(timeval=stamp, localtime=False, usegmt=True)

def _http_to_timestamp(http_datetime_string):
	timestamp = mktime(parsedate(http_datetime_string))
	return str(int(timestamp))

class CompressedResponseProcessor(urllib_request.HTTPBasicAuthHandler):
	# Handler for compressed responses.

	def http_request(self, req):
		req.add_header('Accept-Encoding', 'bzip2,gzip,deflate')
		return req
	https_request = http_request

	def http_response(self, req, response):
		decompressed = None
		if response.headers.get('content-encoding') == 'bzip2':
			import bz2
			decompressed = io.BytesIO(bz2.decompress(response.read()))
		elif response.headers.get('content-encoding') == 'gzip':
			from gzip import GzipFile
			decompressed = GzipFile(fileobj=io.BytesIO(response.read()), mode='r')
		elif response.headers.get('content-encoding') == 'deflate':
			import zlib
			try:
				decompressed = io.BytesIO(zlib.decompress(response.read()))
			except zlib.error: # they ignored RFC1950
				decompressed = io.BytesIO(zlib.decompress(response.read(), -zlib.MAX_WBITS))
		if decompressed:
			old_response = response
			response = urllib_request.addinfourl(decompressed, old_response.headers, old_response.url, old_response.code)
			response.msg = old_response.msg
		return response
	https_response = http_response
