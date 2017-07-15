
import re

from repoman.modules.linechecks.base import LineCheck


class UriUseHttps(LineCheck):
	"""Check that we use https:// for known good sites."""
	repoman_check_name = 'uri.https'
	_SITES = (
		'([-._a-zA-Z0-9]*\.)?apache\.org',
		'((alioth|packages(\.qa)?|people|www)\.)?debian\.org',
		# Most FDO sites support https, but not all (like tango).
		# List the most common ones here for now.
		'((anongit|bugs|cgit|dri|patchwork|people|specifications|www|xcb|xorg)\.)?freedesktop\.org',
		'((bugs|dev|wiki|www)\.)?gentoo\.org',
		'((wiki)\.)?github\.(io|com)',
		'savannah\.(non)?gnu\.org',
		'((gcc|www)\.)?gnu\.org',
		'curl\.haxx\.se',
		'((bugzilla|git|mirrors|patchwork|planet|www(\.wiki)?)\.)?kernel\.org',
		'((bugs|wiki|www)\.)?linuxfoundation\.org',
		'((docs|pypi|www)\.)?python\.org',
		'(sf|sourceforge)\.net',
		'(www\.)?(enlightenment|sourceware|x)\.org',
	)
	# Try to anchor the end of the URL so we don't get false positives
	# with http://github.com.foo.bar.com/.  Unlikely, but possible.
	re = re.compile(r'.*\bhttp://(%s)(\s|["\'/]|$)' % r'|'.join(_SITES))
	error = 'URI_HTTPS'
