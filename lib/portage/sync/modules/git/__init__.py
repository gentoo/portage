# Copyright 2014-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Git plug-in module for portage.
Performs a git pull on repositories."""
__doc__ = doc[:]

from portage.localization import _
from portage.sync.config_checks import CheckSyncConfig
from portage.util import writemsg_level


class CheckGitConfig(CheckSyncConfig):
	def __init__(self, repo, logger):
		CheckSyncConfig.__init__(self, repo, logger)
		self.checks.append('check_depth')
		self.checks.append('check_verify_commit_signature')

	def check_depth(self):
		for attr in ('clone_depth', 'sync_depth'):
			self._check_depth(attr)

	def _check_depth(self, attr):
		d = getattr(self.repo, attr)

		if d is not None:
			try:
				d = int(d)
			except ValueError:
				writemsg_level("!!! %s\n" %
					_("%s value is not a number: '%s'")
					% (attr.replace('_', '-'), d),
					level=self.logger.ERROR, noiselevel=-1)
			else:
				setattr(self.repo, attr, d)

	def check_verify_commit_signature(self):
		v = self.repo.module_specific_options.get(
			'sync-git-verify-commit-signature', 'false').lower()

		if v not in ('yes', 'no', 'true', 'false'):
			writemsg_level("!!! %s\n" %
				_("sync-git-verify-commit-signature not one of: %s")
				% ('{yes, no, true, false}'),
				level=self.logger.ERROR, noiselevel=-1)


module_spec = {
	'name': 'git',
	'description': doc,
	'provides':{
		'git-module': {
			'name': "git",
			'sourcefile': "git",
			'class': "GitSync",
			'description': doc,
			'functions': ['sync', 'new', 'exists', 'retrieve_head'],
			'func_desc': {
				'sync': 'Performs a git pull on the repository',
				'new': 'Creates the new repository at the specified location',
				'exists': 'Returns a boolean of whether the specified dir ' +
					'exists and is a valid Git repository',
				'retrieve_head': 'Returns the head commit hash',
			},
			'validate_config': CheckGitConfig,
			'module_specific_options': (
				'sync-git-clone-env',
				'sync-git-clone-extra-opts',
				'sync-git-env',
				'sync-git-pull-env',
				'sync-git-pull-extra-opts',
				'sync-git-verify-commit-signature',
				),
		}
	}
}
