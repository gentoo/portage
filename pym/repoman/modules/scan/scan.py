# -*- coding:utf-8 -*-

'''
moudules/scan.py
Module specific package scan list generator
'''

import logging
import os
import sys

from repoman.errors import caterror


def scan(repolevel, reposplit, startdir, categories, repo_settings):
	'''Generate a list of pkgs to scan

	@param repolevel: integer, number of subdirectories deep from the tree root
	@param reposplit: list of the path subdirs
	@param startdir: the top level directory to begin scanning from
	@param categories: list of known categories
	@param repo_settings: repository settings instance
	@returns: scanlist, sorted list of pkgs to scan
	'''
	scanlist = []
	if repolevel == 2:
		# we are inside a category directory
		catdir = reposplit[-1]
		if catdir not in categories:
			caterror(catdir, repo_settings.repodir)
		mydirlist = os.listdir(startdir)
		for x in mydirlist:
			if x == "CVS" or x.startswith("."):
				continue
			if os.path.isdir(startdir + "/" + x):
				scanlist.append(catdir + "/" + x)
		# repo_subdir = catdir + os.sep
	elif repolevel == 1:
		for x in categories:
			if not os.path.isdir(startdir + "/" + x):
				continue
			for y in os.listdir(startdir + "/" + x):
				if y == "CVS" or y.startswith("."):
					continue
				if os.path.isdir(startdir + "/" + x + "/" + y):
					scanlist.append(x + "/" + y)
		# repo_subdir = ""
	elif repolevel == 3:
		catdir = reposplit[-2]
		if catdir not in categories:
			caterror(catdir, repo_settings.repodir)
		scanlist.append(catdir + "/" + reposplit[-1])
		# repo_subdir = scanlist[-1] + os.sep
	else:
		msg = 'Repoman is unable to determine PORTDIR or PORTDIR_OVERLAY' + \
			' from the current working directory'
		logging.critical(msg)
		sys.exit(1)

	# repo_subdir_len = len(repo_subdir)
	scanlist.sort()

	logging.debug(
		"Found the following packages to scan:\n%s" % '\n'.join(scanlist))

	return scanlist
