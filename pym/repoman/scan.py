
import logging
import os
import sys
from itertools import chain

from portage import cvstree

from repoman.errors import caterror
from repoman._subprocess import repoman_popen


def scan(repolevel, reposplit, startdir, categories, repo_settings):
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


class Changes(object):
	'''Class object to scan and hold the resultant data
	for all changes to process.

	Basic plan is move the spaghetti code here, refactor the code
	to split it into separate functions for each cvs type.
	Later refactoring can then move the individual scan_ functions
	to their respective VCS plugin module.
	Leaving this class as the manager class which runs the correct VCS plugin.
	This will ease future addition of new VCS types.
	'''

	def __init__(self, options):
		self.options = options
		self._reset()

	def _reset(self):
		self.new_ebuilds = set()
		self.ebuilds = set()
		self.changelogs = set()
		self.changed = []
		self.new = []
		self.removed = []

	def scan(self, vcs_settings):
		self._reset()

		if vcs_settings.vcs:
			vcscheck = getattr(self, 'scan_%s' % vcs_settings.vcs)
			vcscheck()

		if vcs_settings.vcs:
			self.new_ebuilds.update(x for x in self.new if x.endswith(".ebuild"))
			self.ebuilds.update(x for x in self.changed if x.endswith(".ebuild"))
			self.changelogs.update(
				x for x in chain(self.changed, self.new)
				if os.path.basename(x) == "ChangeLog")

	def scan_cvs(self):
		tree = cvstree.getentries("./", recursive=1)
		self.changed = cvstree.findchanged(tree, recursive=1, basedir="./")
		self.new = cvstree.findnew(tree, recursive=1, basedir="./")
		if self.options.if_modified == "y":
			self.removed = cvstree.findremoved(tree, recursive=1, basedir="./")
		del tree

	def scan_svn(self):
		with repoman_popen("svn status") as f:
			svnstatus = f.readlines()
		self.changed = [
			"./" + elem.split()[-1:][0]
			for elem in svnstatus
			if elem and elem[:1] in "MR"]
		self.new = [
			"./" + elem.split()[-1:][0]
			for elem in svnstatus
			if elem.startswith("A")]
		if self.options.if_modified == "y":
			self.removed = [
				"./" + elem.split()[-1:][0]
				for elem in svnstatus
				if elem.startswith("D")]

	def scan_git(self):
		with repoman_popen(
			"git diff-index --name-only "
			"--relative --diff-filter=M HEAD") as f:
			changed = f.readlines()
		self.changed = ["./" + elem[:-1] for elem in changed]
		del changed

		with repoman_popen(
			"git diff-index --name-only "
			"--relative --diff-filter=A HEAD") as f:
			new = f.readlines()
		self.new = ["./" + elem[:-1] for elem in new]
		if self.options.if_modified == "y":
			with repoman_popen(
				"git diff-index --name-only "
				"--relative --diff-filter=D HEAD") as f:
				removed = f.readlines()
			self.removed = ["./" + elem[:-1] for elem in removed]
			del removed

	def scan_bzr(self):
		with repoman_popen("bzr status -S .") as f:
			bzrstatus = f.readlines()
		self.changed = [
			"./" + elem.split()[-1:][0].split('/')[-1:][0]
			for elem in bzrstatus
			if elem and elem[1:2] == "M"]
		self.new = [
			"./" + elem.split()[-1:][0].split('/')[-1:][0]
			for elem in bzrstatus
			if elem and (elem[1:2] == "NK" or elem[0:1] == "R")]
		if self.options.if_modified == "y":
			self.removed = [
				"./" + elem.split()[-3:-2][0].split('/')[-1:][0]
				for elem in bzrstatus
				if elem and (elem[1:2] == "K" or elem[0:1] == "R")]

	def scan_hg(self):
		with repoman_popen("hg status --no-status --modified .") as f:
			changed = f.readlines()
		self.changed = ["./" + elem.rstrip() for elem in changed]
		with repoman_popen("hg status --no-status --added .") as f:
			new = f.readlines()
		self.new = ["./" + elem.rstrip() for elem in new]
		if self.options.if_modified == "y":
			with repoman_popen("hg status --no-status --removed .") as f:
				removed = f.readlines()
			self.removed = ["./" + elem.rstrip() for elem in removed]
		del changed, new, removed
