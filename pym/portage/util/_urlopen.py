# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys

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

def urlopen(url):
	try:
		return _urlopen(url)
	except SystemExit:
		raise
	except Exception:
		if sys.hexversion < 0x3000000:
			raise
		parse_result = urllib_parse.urlparse(url)
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
