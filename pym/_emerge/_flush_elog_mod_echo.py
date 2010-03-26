# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

def _flush_elog_mod_echo():
	"""
	Dump the mod_echo output now so that our other
	notifications are shown last.
	@rtype: bool
	@returns: True if messages were shown, False otherwise.
	"""
	messages_shown = False
	try:
		from portage.elog import mod_echo
	except ImportError:
		pass # happens during downgrade to a version without the module
	else:
		messages_shown = bool(mod_echo._items)
		mod_echo.finalize()
	return messages_shown

