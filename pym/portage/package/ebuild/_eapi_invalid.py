# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import textwrap

import portage
from portage.dep import _repo_separator
from portage.elog import elog_process
from portage.elog.messages import eerror

def eapi_invalid(self, cpv, repo_name, settings,
	eapi_var, eapi_parsed, eapi_lineno):

	msg = []
	msg.extend(textwrap.wrap(("EAPI assignment in ebuild '%s%s%s' does not"
		" conform with PMS section 7.3.1 (see bug #402167):") %
		(cpv, _repo_separator, repo_name), 70))

	if not eapi_parsed:
		# None means the assignment was not found, while an
		# empty string indicates an (invalid) empty assingment.
		msg.append(
			"\tvalid EAPI assignment must"
			" occur on or before line: %s" %
			eapi_lineno)
	else:
		msg.append(("\tbash returned EAPI '%s' which does not match "
			"assignment on line: %s") %
			(eapi_var, eapi_lineno))

	if portage.data.secpass >= 2:
		# TODO: improve elog permission error handling (bug #416231)
		for line in msg:
			eerror(line, phase="other", key=cpv)
		elog_process(cpv, settings,
			phasefilter=("other",))

	else:
		out = portage.output.EOutput()
		for line in msg:
			out.eerror(line)
