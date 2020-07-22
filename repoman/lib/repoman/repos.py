# -*- coding:utf-8 -*-


import io
import logging
import re
import sys
import textwrap

# import our initialized portage instance
from repoman._portage import portage

from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage.checksum import get_valid_checksum_keys

from repoman.errors import err
from repoman.profile import ProfileDesc, valid_profile_types

GPG_KEY_ID_REGEX = r'(0x)?([0-9a-fA-F]{8}){1,5}!?'
bad = portage.output.create_color_func("BAD")


class RepoSettings:
	'''Holds our repo specific settings'''

	def __init__(
		self, config_root, portdir, portdir_overlay,
		repoman_settings=None, vcs_settings=None, options=None,
		qadata=None):
		self.config_root = config_root
		self.repoman_settings = repoman_settings
		self.vcs_settings = vcs_settings

		self.repositories = self.repoman_settings.repositories

		# Ensure that current repository is in the list of enabled repositories.
		self.repodir = os.path.realpath(portdir_overlay)
		try:
			self.repositories.get_repo_for_location(self.repodir)
		except KeyError:
			self._add_repo(config_root, portdir_overlay)

		# Determine the master config loading list
		self.masters_list = []
		# get out repo masters value
		masters = self.repositories.get_repo_for_location(self.repodir).masters
		for repo in masters:
			self.masters_list.append(os.path.join(repo.location, 'metadata', 'repoman'))
		self.masters_list.append(os.path.join(self.repodir, 'metadata', 'repoman'))

		logging.debug("RepoSettings: init(); load qadata")
		# load the repo specific configuration
		self.qadata = qadata
		if not self.qadata.load_repo_config(self.masters_list, options, repoman_settings.valid_versions):
			logging.error("Aborting...")
			sys.exit(1)
		logging.debug("RepoSettings: qadata loaded: %s", qadata.no_exec)

		self.root = self.repoman_settings['EROOT']
		self.trees = {
			self.root: {'porttree': portage.portagetree(settings=self.repoman_settings)}
		}
		self.portdb = self.trees[self.root]['porttree'].dbapi

		# Constrain dependency resolution to the master(s)
		# that are specified in layout.conf.
		self.repo_config = self.repositories.get_repo_for_location(self.repodir)
		self.portdb.porttrees = list(self.repo_config.eclass_db.porttrees)
		self.portdir = self.portdb.porttrees[0]
		self.commit_env = os.environ.copy()
		# list() is for iteration on a copy.
		for repo in list(self.repositories):
			# all paths are canonical
			if repo.location not in self.repo_config.eclass_db.porttrees:
				del self.repositories[repo.name]

		if self.repo_config.sign_commit and options.mode in ("commit", "fix", "manifest"):
			if vcs_settings.vcs:
				func = getattr(self, '_vcs_gpg_%s' % vcs_settings.vcs)
				func()
			else:
				logging.warning("No VCS type detected, unable to sign the commit")

		# In order to disable manifest signatures, repos may set
		# "sign-manifests = false" in metadata/layout.conf. This
		# can be used to prevent merge conflicts like those that
		# thin-manifests is designed to prevent.
		self.sign_manifests = "sign" in self.repoman_settings.features and \
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
		valid_gpg_key = self.repoman_settings.get("PORTAGE_GPG_KEY") and re.match(
			r'^%s$' % GPG_KEY_ID_REGEX, self.repoman_settings["PORTAGE_GPG_KEY"])

		if self.sign_manifests and is_commit and not valid_gpg_key:
			logging.error(
				"PORTAGE_GPG_KEY value is invalid: %s" %
				self.repoman_settings["PORTAGE_GPG_KEY"])
			sys.exit(1)

		manifest_hashes = self.repo_config.manifest_hashes
		manifest_required_hashes = self.repo_config.manifest_required_hashes
		if manifest_hashes is None:
			manifest_hashes = portage.const.MANIFEST2_HASH_DEFAULTS
			manifest_required_hashes = manifest_hashes

		if options.mode in ("commit", "fix", "manifest"):
			missing_required_hashes = manifest_required_hashes.difference(
				manifest_hashes)
			if missing_required_hashes:
				msg = (
					"The 'manifest-hashes' setting in the '%s' repository's "
					"metadata/layout.conf does not contain the '%s' hashes which "
					"are listed in 'manifest-required-hashes'. Please fix that "
					"file if you want to generate valid manifests for "
					"this repository.") % (
					self.repo_config.name, ' '.join(missing_required_hashes))
				for line in textwrap.wrap(msg, 70):
					logging.error(line)
				sys.exit(1)

			unsupported_hashes = manifest_hashes.difference(
				get_valid_checksum_keys())
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

	def _add_repo(self, config_root, portdir_overlay):
		self.repo_conf = portage.repository.config
		self.repo_name = self.repo_conf.RepoConfig._read_valid_repo_name(
			portdir_overlay)[0]
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
		self.repoman_settings['PORTDIR_OVERLAY'] = "%s %s" % (
			self.repoman_settings.get('PORTDIR_OVERLAY', ''),
			portage._shell_quote(portdir_overlay))
		self.repositories = self.repo_conf.load_repository_config(
			self.repoman_settings, extra_files=[tmp_conf_file])
		# We have to call the config constructor again so that attributes
		# dependent on config.repositories are initialized correctly.
		self.repoman_settings = portage.config(
			config_root=config_root, local_config=False,
			repositories=self.repositories)

	##########
	# future vcs plugin functions
	##########

	def _vcs_gpg_bzr(self):
		pass

	def _vcs_gpg_cvs(self):
		pass

	def _vcs_gpg_git(self):
		# NOTE: It's possible to use --gpg-sign=key_id to specify the key in
		# the commit arguments. If key_id is unspecified, then it must be
		# configured by `git config user.signingkey key_id`.
		self.vcs_settings.vcs_local_opts.append("--gpg-sign")
		if self.repoman_settings.get("PORTAGE_GPG_DIR"):
			# Pass GNUPGHOME to git for bug #462362.
			self.commit_env["GNUPGHOME"] = self.repoman_settings["PORTAGE_GPG_DIR"]

		# Pass GPG_TTY to git for bug #477728.
		try:
			self.commit_env["GPG_TTY"] = os.ttyname(sys.stdin.fileno())
		except OSError:
			pass

	def _vcs_gpg_hg(self):
		pass

	def _vcs_gpg_svn(self):
		pass


def list_checks(kwlist, liclist, uselist, repoman_settings):
	liclist_deprecated = set()
	if "DEPRECATED" in repoman_settings._license_manager._license_groups:
		liclist_deprecated.update(
			repoman_settings._license_manager.expandLicenseTokens(["@DEPRECATED"]))

	if not liclist:
		logging.fatal("Couldn't find licenses?")
		sys.exit(1)

	if not kwlist:
		logging.fatal("Couldn't read KEYWORDS from arch.list")
		sys.exit(1)

	if not uselist:
		logging.fatal("Couldn't find use.desc?")
		sys.exit(1)
	return liclist_deprecated


def repo_metadata(portdb, repoman_settings):
	# get lists of valid keywords, licenses, and use
	kwlist = set()
	liclist = set()
	uselist = set()
	profile_list = []
	global_pmasklines = []

	for path in portdb.porttrees:
		try:
			liclist.update(os.listdir(os.path.join(path, "licenses")))
		except OSError:
			pass
		kwlist.update(
			portage.grabfile(os.path.join(path, "profiles", "arch.list")))

		use_desc = portage.grabfile(os.path.join(path, 'profiles', 'use.desc'))
		for x in use_desc:
			x = x.split()
			if x:
				uselist.add(x[0])

		expand_desc_dir = os.path.join(path, 'profiles', 'desc')
		try:
			expand_list = os.listdir(expand_desc_dir)
		except OSError:
			pass
		else:
			for fn in expand_list:
				if not fn[-5:] == '.desc':
					continue
				use_prefix = fn[:-5].lower() + '_'
				for x in portage.grabfile(os.path.join(expand_desc_dir, fn)):
					x = x.split()
					if x:
						uselist.add(use_prefix + x[0])

		global_pmasklines.append(
			portage.util.grabfile_package(
				os.path.join(path, 'profiles', 'package.mask'),
				recursive=1, verify_eapi=True))

		desc_path = os.path.join(path, 'profiles', 'profiles.desc')
		try:
			desc_file = io.open(
				_unicode_encode(
					desc_path, encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'], errors='replace')
		except EnvironmentError:
			pass
		else:
			for i, x in enumerate(desc_file):
				if x[0] == "#":
					continue
				arch = x.split()
				if len(arch) == 0:
					continue
				if len(arch) != 3:
					err(
						"wrong format: \"%s\" in %s line %d" %
						(bad(x.strip()), desc_path, i + 1, ))
				elif arch[0] not in kwlist:
					err(
						"invalid arch: \"%s\" in %s line %d" %
						(bad(arch[0]), desc_path, i + 1, ))
				elif arch[2] not in valid_profile_types:
					err(
						"invalid profile type: \"%s\" in %s line %d" %
						(bad(arch[2]), desc_path, i + 1, ))
				profile_desc = ProfileDesc(arch[0], arch[2], arch[1], path)
				if not os.path.isdir(profile_desc.abs_path):
					logging.error(
						"Invalid %s profile (%s) for arch %s in %s line %d",
						arch[2], arch[1], arch[0], desc_path, i + 1)
					continue
				if os.path.exists(
					os.path.join(profile_desc.abs_path, 'deprecated')):
					continue
				profile_list.append(profile_desc)
			desc_file.close()

	global_pmasklines = portage.util.stack_lists(global_pmasklines, incremental=1)
	global_pmaskdict = {}
	for x in global_pmasklines:
		global_pmaskdict.setdefault(x.cp, []).append(x)
	del global_pmasklines

	return (
		kwlist, liclist, uselist, profile_list, global_pmaskdict,
		list_checks(kwlist, liclist, uselist, repoman_settings))
