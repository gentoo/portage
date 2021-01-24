
import re # pylint: disable=unused-import

from repoman.modules.linechecks.base import LineCheck


class UriUseHttps(LineCheck):
	"""Check that we use https:// for known good sites."""
	repoman_check_name = 'uri.https'
	_SITES = (
		r'([-._a-zA-Z0-9]*\.)?apache\.org',
		r'((alioth|packages(\.qa)?|people|www)\.)?debian\.org',
		# Most FDO sites support https, but not all (like tango).
		# List the most common ones here for now.
		r'((anongit|bugs|cgit|dri|patchwork|people|specifications|www|xcb|xorg)\.)?freedesktop\.org',
		r'((bugs|dev|wiki|www)\.)?gentoo\.org',
		r'((wiki)\.)?github\.(io|com)',
		r'savannah\.(non)?gnu\.org',
		r'((gcc|www)\.)?gnu\.org',
		r'curl\.haxx\.se',
		r'((bugzilla|git|mirrors|patchwork|planet|www(\.wiki)?)\.)?kernel\.org',
		r'((bugs|wiki|www)\.)?linuxfoundation\.org',
		r'((docs|pypi|www)\.)?python\.org',
		r'(sf|sourceforge)\.net',
		r'(www\.)?(enlightenment|sourceware|x)\.org',
	)
	# Try to anchor the end of the URL so we don't get false positives
	# with http://github.com.foo.bar.com/.  Unlikely, but possible.
	re = re.compile(r'.*\bhttp://(%s)(\s|["\'/]|$)' % r'|'.join(_SITES))
	error = 'URI_HTTPS'
