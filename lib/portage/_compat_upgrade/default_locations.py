# Copyright 2018-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import re

import portage
from portage import os
from portage.const import GLOBAL_CONFIG_PATH

COMPAT_DISTDIR = 'usr/portage/distfiles'
COMPAT_PKGDIR = 'usr/portage/packages'
COMPAT_RPMDIR = 'usr/portage/rpm'
COMPAT_MAIN_REPO = 'usr/portage'


def main():
	"""
	If the current installation is still configured to use any of the
	legacy default /usr/portage locations, then patch make.globals and
	repos.conf inside ${ED} to maintain compatible defaults. This is
	intended to be called from the ebuild as follows:

	pkg_preinst() {
		python_setup
		python_export PYTHON_SITEDIR
		env -u DISTDIR \
			-u PORTAGE_OVERRIDE_EPREFIX \
			-u PORTAGE_REPOSITORIES \
			-u PORTDIR \
			-u PORTDIR_OVERLAY \
			PYTHONPATH="${ED%/}${PYTHON_SITEDIR}${PYTHONPATH:+:${PYTHONPATH}}" \
			"${PYTHON}" -m portage._compat_upgrade.default_locations || die
	}
	"""
	out = portage.output.EOutput()
	config = portage.settings

	compat_distdir = os.path.join(portage.const.EPREFIX or '/', COMPAT_DISTDIR)
	try:
		do_distdir = os.path.samefile(config['DISTDIR'], compat_distdir)
	except OSError:
		do_distdir = False

	compat_pkgdir = os.path.join(portage.const.EPREFIX or '/', COMPAT_PKGDIR)
	try:
		do_pkgdir = os.path.samefile(config['PKGDIR'], compat_pkgdir)
	except OSError:
		do_pkgdir = False

	compat_rpmdir = os.path.join(portage.const.EPREFIX or '/', COMPAT_RPMDIR)
	try:
		do_rpmdir = os.path.samefile(config['RPMDIR'], compat_rpmdir)
	except OSError:
		do_rpmdir = False

	compat_main_repo = os.path.join(portage.const.EPREFIX or '/', COMPAT_MAIN_REPO)
	try:
		do_main_repo = os.path.samefile(config.repositories.mainRepoLocation(), compat_main_repo)
	except OSError:
		do_main_repo = False

	if do_distdir or do_pkgdir or do_rpmdir:
		config_path = os.path.join(os.environ['ED'], GLOBAL_CONFIG_PATH.lstrip(os.sep), 'make.globals')
		with open(config_path) as f:
			content = f.read()
			if do_distdir:
				compat_setting = 'DISTDIR="{}"'.format(compat_distdir)
				out.einfo('Setting make.globals default {} for backward compatibility'.format(compat_setting))
				content = re.sub('^DISTDIR=.*$', compat_setting, content, flags=re.MULTILINE)
			if do_pkgdir:
				compat_setting = 'PKGDIR="{}"'.format(compat_pkgdir)
				out.einfo('Setting make.globals default {} for backward compatibility'.format(compat_setting))
				content = re.sub('^PKGDIR=.*$', compat_setting, content, flags=re.MULTILINE)
			if do_rpmdir:
				compat_setting = 'RPMDIR="{}"'.format(compat_rpmdir)
				out.einfo('Setting make.globals default {} for backward compatibility'.format(compat_setting))
				content = re.sub('^RPMDIR=.*$', compat_setting, content, flags=re.MULTILINE)
		with open(config_path, 'wt') as f:
			f.write(content)

	if do_main_repo:
		config_path = os.path.join(os.environ['ED'], GLOBAL_CONFIG_PATH.lstrip(os.sep), 'repos.conf')
		with open(config_path) as f:
			content = f.read()
			compat_setting = 'location = {}'.format(compat_main_repo)
			out.einfo('Setting repos.conf default {} for backward compatibility'.format(compat_setting))
			content = re.sub('^location =.*$', compat_setting, content, flags=re.MULTILINE)
		with open(config_path, 'wt') as f:
			f.write(content)


if __name__ == '__main__':
	main()
