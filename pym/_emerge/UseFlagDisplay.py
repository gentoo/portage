# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from itertools import chain
import sys

from portage import _encodings, _unicode_decode, _unicode_encode
from portage.output import red
from portage.util import cmp_sort_key
from portage.output import blue

class UseFlagDisplay(object):

	__slots__ = ('name', 'enabled', 'forced')

	def __init__(self, name, enabled, forced):
		self.name = name
		self.enabled = enabled
		self.forced = forced

	def __str__(self):
		s = self.name
		if self.enabled:
			s = red(s)
		else:
			s = '-' + s
			s = blue(s)
		if self.forced:
			s = '(%s)' % s
		return s

	if sys.hexversion < 0x3000000:

		__unicode__ = __str__

		def __str__(self):
			return _unicode_encode(self.__unicode__(),
				encoding=_encodings['content'])

	def _cmp_combined(a, b):
		"""
		Sort by name, combining enabled and disabled flags.
		"""
		return (a.name > b.name) - (a.name < b.name)

	sort_combined = cmp_sort_key(_cmp_combined)
	del _cmp_combined

	def _cmp_separated(a, b):
		"""
		Sort by name, separating enabled flags from disabled flags.
		"""
		enabled_diff = b.enabled - a.enabled
		if enabled_diff:
			return enabled_diff
		return (a.name > b.name) - (a.name < b.name)

	sort_separated = cmp_sort_key(_cmp_separated)
	del _cmp_separated

def pkg_use_display(pkg, opts, modified_use=None):
	settings = pkg.root_config.settings
	use_expand = pkg.use.expand
	use_expand_hidden = pkg.use.expand_hidden
	alphabetical_use = '--alphabetical' in opts
	forced_flags = set(chain(pkg.use.force,
		pkg.use.mask))
	if modified_use is None:
		use = set(pkg.use.enabled)
	else:
		use = set(modified_use)
	use.discard(settings.get('ARCH'))
	use_expand_flags = set()
	use_enabled = {}
	use_disabled = {}
	for varname in use_expand:
		flag_prefix = varname.lower() + "_"
		for f in use:
			if f.startswith(flag_prefix):
				use_expand_flags.add(f)
				use_enabled.setdefault(
					varname.upper(), []).append(f[len(flag_prefix):])

		for f in pkg.iuse.all:
			if f.startswith(flag_prefix):
				use_expand_flags.add(f)
				if f not in use:
					use_disabled.setdefault(
						varname.upper(), []).append(f[len(flag_prefix):])

	var_order = set(use_enabled)
	var_order.update(use_disabled)
	var_order = sorted(var_order)
	var_order.insert(0, 'USE')
	use.difference_update(use_expand_flags)
	use_enabled['USE'] = list(use)
	use_disabled['USE'] = []

	for f in pkg.iuse.all:
		if f not in use and \
			f not in use_expand_flags:
			use_disabled['USE'].append(f)

	flag_displays = []
	for varname in var_order:
		if varname.lower() in use_expand_hidden:
			continue
		flags = []
		for f in use_enabled.get(varname, []):
			flags.append(UseFlagDisplay(f, True, f in forced_flags))
		for f in use_disabled.get(varname, []):
			flags.append(UseFlagDisplay(f, False, f in forced_flags))
		if alphabetical_use:
			flags.sort(key=UseFlagDisplay.sort_combined)
		else:
			flags.sort(key=UseFlagDisplay.sort_separated)
		# Use _unicode_decode() to force unicode format string so
		# that UseFlagDisplay.__unicode__() is called in python2.
		flag_displays.append('%s="%s"' % (varname,
			' '.join(_unicode_decode("%s") % (f,) for f in flags)))

	return ' '.join(flag_displays)
