# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.process import find_binary
from portage.util import shlex_split

def validate_cmd_var(v):
	"""
	Validate an evironment variable value to see if it
	contains an executable command as the first token.
	returns (valid, token_list) where 'valid' is boolean and 'token_list'
	is the (possibly empty) list of tokens split by shlex.
	"""
	invalid = False
	v_split = shlex_split(v)
	if not v_split:
		invalid = True
	elif os.path.isabs(v_split[0]):
		invalid = not os.access(v_split[0], os.EX_OK)
	elif find_binary(v_split[0]) is None:
		invalid = True
	return (not invalid, v_split)
