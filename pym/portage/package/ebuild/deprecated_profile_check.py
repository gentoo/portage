# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['deprecated_profile_check']

import io

from portage import os, _encodings, _unicode_encode
from portage.const import DEPRECATED_PROFILE_FILE
from portage.localization import _
from portage.output import colorize
from portage.util import writemsg

def deprecated_profile_check(settings=None):
	config_root = "/"
	deprecated_profile_file = None
	if settings is not None:
		config_root = settings["PORTAGE_CONFIGROOT"]
		for x in reversed(settings.profiles):
			deprecated_profile_file = os.path.join(x, "deprecated")
			if os.access(deprecated_profile_file, os.R_OK):
				break
		else:
			deprecated_profile_file = None

	if deprecated_profile_file is None:
		deprecated_profile_file = os.path.join(config_root,
			DEPRECATED_PROFILE_FILE)
		if not os.access(deprecated_profile_file, os.R_OK):
			deprecated_profile_file = os.path.join(config_root,
				'etc', 'make.profile', 'deprecated')
			if not os.access(deprecated_profile_file, os.R_OK):
				return

	dcontent = io.open(_unicode_encode(deprecated_profile_file,
		encoding=_encodings['fs'], errors='strict'), 
		mode='r', encoding=_encodings['content'], errors='replace').readlines()
	writemsg(colorize("BAD", _("\n!!! Your current profile is "
		"deprecated and not supported anymore.")) + "\n", noiselevel=-1)
	writemsg(colorize("BAD", _("!!! Use eselect profile to update your "
		"profile.")) + "\n", noiselevel=-1)
	if not dcontent:
		writemsg(colorize("BAD", _("!!! Please refer to the "
			"Gentoo Upgrading Guide.")) + "\n", noiselevel=-1)
		return True
	newprofile = dcontent[0]
	writemsg(colorize("BAD", _("!!! Please upgrade to the "
		"following profile if possible:")) + "\n", noiselevel=-1)
	writemsg(8*" " + colorize("GOOD", newprofile) + "\n", noiselevel=-1)
	if len(dcontent) > 1:
		writemsg(_("To upgrade do the following steps:\n"), noiselevel=-1)
		for myline in dcontent[1:]:
			writemsg(myline, noiselevel=-1)
		writemsg("\n\n", noiselevel=-1)
	return True
