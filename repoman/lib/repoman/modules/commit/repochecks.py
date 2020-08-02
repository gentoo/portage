# -*- coding:utf-8 -*-

from __future__ import print_function

from portage.output import red

from repoman.errors import err


def commit_check(repolevel, reposplit):
	# Check if it's in $PORTDIR/$CATEGORY/$PN , otherwise bail if commiting.
	# Reason for this is if they're trying to commit in just $FILESDIR/*,
	# the Manifest needs updating.
	# This check ensures that repoman knows where it is,
	# and the manifest recommit is at least possible.
	if repolevel not in [1, 2, 3]:
		print(red("***") + (
			" Commit attempts *must* be from within a vcs checkout,"
			" category, or package directory."))
		print(red("***") + (
			" Attempting to commit from a packages files directory"
			" will be blocked for instance."))
		print(red("***") + (
			" This is intended behaviour,"
			" to ensure the manifest is recommitted for a package."))
		print(red("***"))
		err(
			"Unable to identify level we're commiting from for %s" %
			'/'.join(reposplit))


def conflict_check(vcs_settings, options):
	if vcs_settings.vcs:
		conflicts = vcs_settings.status.detect_conflicts(options)

