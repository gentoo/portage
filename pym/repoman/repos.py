

import io
import logging
import re
import sys
import textwrap

import portage
from portage import os


GPG_KEY_ID_REGEX = r'(0x)?([0-9a-fA-F]{8}){1,5}!?'


class RepoSettings(object):
	'''Holds out repo specific settings'''

	def __init__(self, config_root, portdir, portdir_overlay,
		repoman_settings=None, vcs_settings=None, options=None,
		qawarnings=None):
		# Ensure that current repository is in the list of enabled repositories.
		self.repodir = os.path.realpath(portdir_overlay)
		try:
			repoman_settings.repositories.get_repo_for_location(self.repodir)
		except KeyError:
			self.repo_conf = portage.repository.config
			self.repo_name = self.repo_conf.RepoConfig._read_valid_repo_name(portdir_overlay)[0]
			self.layout_conf_data = self.repo_conf.parse_layout_conf(portdir_overlay)[0]
			if self.layout_conf_data['repo-name']:
				self.repo_name = self.layout_conf_data['repo-name']
			tmp_conf_file = io.StringIO(textwrap.dedent("""
				[%s]
				location = %s
				""") % (self.repo_name, portdir_overlay))
			# Ensure that the repository corresponding to $PWD overrides a
			# repository of the same name referenced by the existing PORTDIR
			# or PORTDIR_OVERLAY settings.
			repoman_settings['PORTDIR_OVERLAY'] = "%s %s" % (
				repoman_settings.get('PORTDIR_OVERLAY', ''),
				portage._shell_quote(portdir_overlay))
			self.repositories = self.repo_conf.load_repository_config(
				repoman_settings, extra_files=[tmp_conf_file])
			# We have to call the config constructor again so that attributes
			# dependent on config.repositories are initialized correctly.
			repoman_settings = portage.config(
				config_root=config_root, local_config=False, repositories=self.repositories)

		self.root = repoman_settings['EROOT']
		self.trees = {
			self.root: {'porttree': portage.portagetree(settings=repoman_settings)}
		}
		self.portdb = self.trees[self.root]['porttree'].dbapi

		# Constrain dependency resolution to the master(s)
		# that are specified in layout.conf.
		self.repo_config = repoman_settings.repositories.get_repo_for_location(self.repodir)
		self.portdb.porttrees = list(self.repo_config.eclass_db.porttrees)
		self.portdir = self.portdb.porttrees[0]
		self.commit_env = os.environ.copy()
		# list() is for iteration on a copy.
		for repo in list(repoman_settings.repositories):
			# all paths are canonical
			if repo.location not in self.repo_config.eclass_db.porttrees:
				del repoman_settings.repositories[repo.name]

		if self.repo_config.allow_provide_virtual:
			qawarnings.add("virtual.oldstyle")

		if self.repo_config.sign_commit:
			if vcs_settings.vcs == 'git':
				# NOTE: It's possible to use --gpg-sign=key_id to specify the key in
				# the commit arguments. If key_id is unspecified, then it must be
				# configured by `git config user.signingkey key_id`.
				vcs_settings.vcs_local_opts.append("--gpg-sign")
				if repoman_settings.get("PORTAGE_GPG_DIR"):
					# Pass GNUPGHOME to git for bug #462362.
					self.commit_env["GNUPGHOME"] = repoman_settings["PORTAGE_GPG_DIR"]

				# Pass GPG_TTY to git for bug #477728.
				try:
					self.commit_env["GPG_TTY"] = os.ttyname(sys.stdin.fileno())
				except OSError:
					pass

		# In order to disable manifest signatures, repos may set
		# "sign-manifests = false" in metadata/layout.conf. This
		# can be used to prevent merge conflicts like those that
		# thin-manifests is designed to prevent.
		self.sign_manifests = "sign" in repoman_settings.features and \
			self.repo_config.sign_manifest

		if self.repo_config.sign_manifest and self.repo_config.name == "gentoo" and \
			options.mode in ("commit",) and not self.sign_manifests:
			msg = (
				"The '%s' repository has manifest signatures enabled, "
				"but FEATURES=sign is currently disabled. In order to avoid this "
				"warning, enable FEATURES=sign in make.conf. Alternatively, "
				"repositories can disable manifest signatures by setting "
				"'sign-manifests = false' in metadata/layout.conf.") % (
					self.repo_config.name,)
			for line in textwrap.wrap(msg, 60):
				logging.warn(line)

		is_commit = options.mode in ("commit",)
		valid_gpg_key = repoman_settings.get("PORTAGE_GPG_KEY") and re.match(
			r'^%s$' % GPG_KEY_ID_REGEX, repoman_settings["PORTAGE_GPG_KEY"])

		if self.sign_manifests and is_commit and not valid_gpg_key:
			logging.error(
				"PORTAGE_GPG_KEY value is invalid: %s" %
				repoman_settings["PORTAGE_GPG_KEY"])
			sys.exit(1)

		manifest_hashes = self.repo_config.manifest_hashes
		if manifest_hashes is None:
			manifest_hashes = portage.const.MANIFEST2_HASH_DEFAULTS

		if options.mode in ("commit", "fix", "manifest"):
			if portage.const.MANIFEST2_REQUIRED_HASH not in manifest_hashes:
				msg = (
					"The 'manifest-hashes' setting in the '%s' repository's "
					"metadata/layout.conf does not contain the '%s' hash which "
					"is required by this portage version. You will have to "
					"upgrade portage if you want to generate valid manifests for "
					"this repository.") % (
					self.repo_config.name, portage.const.MANIFEST2_REQUIRED_HASH)
				for line in textwrap.wrap(msg, 70):
					logging.error(line)
				sys.exit(1)

			unsupported_hashes = manifest_hashes.difference(
				portage.const.MANIFEST2_HASH_FUNCTIONS)
			if unsupported_hashes:
				msg = (
					"The 'manifest-hashes' setting in the '%s' repository's "
					"metadata/layout.conf contains one or more hash types '%s' "
					"which are not supported by this portage version. You will "
					"have to upgrade portage if you want to generate valid "
					"manifests for this repository.") % (
					self.repo_config.name, " ".join(sorted(unsupported_hashes)))
				for line in textwrap.wrap(msg, 70):
					logging.error(line)
				sys.exit(1)
