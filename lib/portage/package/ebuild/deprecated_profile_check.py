# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ['deprecated_profile_check']

import io

import portage
from portage import os, _encodings, _unicode_encode
from portage.const import DEPRECATED_PROFILE_FILE
from portage.localization import _
from portage.output import colorize
from portage.util import writemsg

def deprecated_profile_check(settings=None):
	config_root = None
	eprefix = None
	deprecated_profile_file = None
	if settings is not None:
		config_root = settings["PORTAGE_CONFIGROOT"]
		eprefix = settings["EPREFIX"]
		for x in reversed(settings._locations_manager.profiles_complex):
			if x.show_deprecated_warning:
				deprecated_profile_file = os.path.join(x.location, "deprecated")
				if os.access(deprecated_profile_file, os.R_OK):
					break
		else:
			deprecated_profile_file = None

	if deprecated_profile_file is None:
		deprecated_profile_file = os.path.join(config_root or "/",
			DEPRECATED_PROFILE_FILE)
		if not os.access(deprecated_profile_file, os.R_OK):
			deprecated_profile_file = os.path.join(config_root or "/",
				'etc', 'make.profile', 'deprecated')
			if not os.access(deprecated_profile_file, os.R_OK):
				return

	with io.open(_unicode_encode(deprecated_profile_file,
		encoding=_encodings['fs'], errors='strict'),
		mode='r', encoding=_encodings['content'], errors='replace') as f:
		dcontent = f.readlines()
	writemsg(colorize("BAD", _("\n!!! Your current profile is "
		"deprecated and not supported anymore.")) + "\n", noiselevel=-1)
	writemsg(colorize("BAD", _("!!! Use eselect profile to update your "
		"profile.")) + "\n", noiselevel=-1)
	if not dcontent:
		writemsg(colorize("BAD", _("!!! Please refer to the "
			"Gentoo Upgrading Guide.")) + "\n", noiselevel=-1)
		return True
	newprofile = dcontent[0].rstrip("\n")
	writemsg(colorize("BAD", _("!!! Please upgrade to the "
		"following profile if possible:")) + "\n\n", noiselevel=-1)
	writemsg(8*" " + colorize("GOOD", newprofile) + "\n\n", noiselevel=-1)
	if len(dcontent) > 1:
		writemsg(_("To upgrade do the following steps:\n"), noiselevel=-1)
		for myline in dcontent[1:]:
			writemsg(myline, noiselevel=-1)
		writemsg("\n\n", noiselevel=-1)
	else:
		writemsg(_("You may use the following command to upgrade:\n\n"), noiselevel=-1)
		writemsg(8*" " + colorize("INFORM", 'eselect profile set ' +
			newprofile) + "\n\n", noiselevel=-1)

	if settings is not None:
		main_repo_loc = settings.repositories.mainRepoLocation()
		new_profile_path = os.path.join(main_repo_loc,
			"profiles", newprofile.rstrip("\n"))

		if os.path.isdir(new_profile_path):
			new_config = portage.config(config_root=config_root,
				config_profile_path=new_profile_path,
				eprefix=eprefix)

			if not new_config.profiles:
				writemsg("\n %s %s\n" % (colorize("WARN", "*"),
					_("You must update portage before you "
					"can migrate to the above profile.")), noiselevel=-1)
				writemsg(" %s %s\n\n" % (colorize("WARN", "*"),
					_("In order to update portage, "
					"run 'emerge --oneshot sys-apps/portage'.")),
					noiselevel=-1)

	return True
