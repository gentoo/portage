# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import select
class PollConstants:

	"""
	Provides POLL* constants that are equivalent to those from the
	select module, for use by PollSelectAdapter.
	"""

	names = ("POLLIN", "POLLPRI", "POLLOUT", "POLLERR", "POLLHUP", "POLLNVAL")
	v = 1
	for k in names:
		locals()[k] = getattr(select, k, v)
		v *= 2
	del k, v
