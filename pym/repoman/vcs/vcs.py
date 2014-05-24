

def vcs_files_to_cps(vcs_file_iter):
	"""
	Iterate over the given modified file paths returned from the vcs,
	and return a frozenset containing category/pn strings for each
	modified package.
	"""

	modified_cps = []

	if repolevel == 3:
		if reposplit[-2] in categories and \
			next(vcs_file_iter, None) is not None:
			modified_cps.append("/".join(reposplit[-2:]))

	elif repolevel == 2:
		category = reposplit[-1]
		if category in categories:
			for filename in vcs_file_iter:
				f_split = filename.split(os.sep)
				# ['.', pn, ...]
				if len(f_split) > 2:
					modified_cps.append(category + "/" + f_split[1])

	else:
		# repolevel == 1
		for filename in vcs_file_iter:
			f_split = filename.split(os.sep)
			# ['.', category, pn, ...]
			if len(f_split) > 3 and f_split[1] in categories:
				modified_cps.append("/".join(f_split[1:3]))

	return frozenset(modified_cps)


def vcs_new_changed(relative_path):
	for x in chain(mychanged, mynew):
		if x == relative_path:
			return True
	return False


def git_supports_gpg_sign():
	status, cmd_output = \
		repoman_getstatusoutput("git --version")
	cmd_output = cmd_output.split()
	if cmd_output:
		version = re.match(r'^(\d+)\.(\d+)\.(\d+)', cmd_output[-1])
		if version is not None:
			version = [int(x) for x in version.groups()]
			if version[0] > 1 or \
				(version[0] == 1 and version[1] > 7) or \
				(version[0] == 1 and version[1] == 7 and version[2] >= 9):
				return True
	return False
