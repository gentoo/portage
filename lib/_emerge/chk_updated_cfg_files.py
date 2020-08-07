# Copyright 1999-2012, 2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging

import portage
from portage import os
from portage.localization import _
from portage.output import bold, colorize, yellow
from portage.util import writemsg_level

def chk_updated_cfg_files(eroot, config_protect):
	target_root = eroot
	result = list(
		portage.util.find_updated_config_files(target_root, config_protect))

	for x in result:
		writemsg_level("\n %s " % (colorize("WARN", "* " + _("IMPORTANT:"))),
			level=logging.INFO, noiselevel=-1)
		if not x[1]: # it's a protected file
			writemsg_level( _("config file '%s' needs updating.\n") % x[0],
				level=logging.INFO, noiselevel=-1)
		else: # it's a protected dir
			if len(x[1]) == 1:
				head, tail = os.path.split(x[1][0])
				tail = tail[len("._cfg0000_"):]
				fpath = os.path.join(head, tail)
				writemsg_level(_("config file '%s' needs updating.\n") % fpath,
					level=logging.INFO, noiselevel=-1)
			else:
				writemsg_level(
					_("%d config files in '%s' need updating.\n") % \
					(len(x[1]), x[0]), level=logging.INFO, noiselevel=-1)

	if result:
		print(" " + yellow("*") + " See the " +
			colorize("INFORM", _("CONFIGURATION FILES")) + " and " +
			colorize("INFORM", _("CONFIGURATION FILES UPDATE TOOLS")))
		print(" " + yellow("*") + " sections of the " + bold("emerge") + " " +
			_("man page to learn how to update config files."))
