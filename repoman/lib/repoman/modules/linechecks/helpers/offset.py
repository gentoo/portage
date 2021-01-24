
import re # pylint: disable=unused-import

from repoman.modules.linechecks.base import LineCheck


class NoOffsetWithHelpers(LineCheck):
	""" Check that the image location, the alternate root offset, and the
	offset prefix (D, ROOT, ED, EROOT and EPREFIX) are not used with
	helpers """

	repoman_check_name = 'variable.usedwithhelpers'
	# Ignore matches in quoted strings like this:
	# elog "installed into ${ROOT}usr/share/php5/apc/."
	_install_funcs = (
		'docinto|do(compress|dir|hard)'
		'|exeinto|fowners|fperms|insinto|into')
	_quoted_vars = 'D|ROOT|ED|EROOT|EPREFIX'
	re = re.compile(
		r'^[^#"\']*\b(%s)\s+"?\$\{?(%s)\b.*' %
		(_install_funcs, _quoted_vars))
	error = 'NO_OFFSET_WITH_HELPERS'
