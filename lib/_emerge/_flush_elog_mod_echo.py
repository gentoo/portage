# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.elog import mod_echo

def _flush_elog_mod_echo():
	"""
	Dump the mod_echo output now so that our other
	notifications are shown last.
	@rtype: bool
	@return: True if messages were shown, False otherwise.
	"""
	messages_shown = bool(mod_echo._items)
	mod_echo.finalize()
	return messages_shown
