# Copyright 1999-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging
import textwrap
import portage
from portage import os
from portage.util import writemsg_level

def show_invalid_depstring_notice(parent_node, error_msg):

	msg1 = "\n\n!!! Invalid or corrupt dependency specification: " + \
		"\n\n%s\n\n%s\n\n" % (error_msg, parent_node)
	p_key = parent_node.cpv
	p_status = parent_node.operation
	msg = []
	if p_status == "nomerge":
		category, pf = portage.catsplit(p_key)
		pkg_location = os.path.join(parent_node.root_config.settings['EROOT'], portage.VDB_PATH, category, pf)
		msg.append("Portage is unable to process the dependencies of the ")
		msg.append("'%s' package. " % p_key)
		msg.append("In order to correct this problem, the package ")
		msg.append("should be uninstalled, reinstalled, or upgraded. ")
		msg.append("As a temporary workaround, the --nodeps option can ")
		msg.append("be used to ignore all dependencies.  For reference, ")
		msg.append("the problematic dependencies can be found in the ")
		msg.append("*DEPEND files located in '%s/'." % pkg_location)
	else:
		msg.append("This package can not be installed. ")
		msg.append("Please notify the '%s' package maintainer " % p_key)
		msg.append("about this problem.")

	msg2 = "".join("%s\n" % line for line in textwrap.wrap("".join(msg), 72))
	writemsg_level(msg1 + msg2, level=logging.ERROR, noiselevel=-1)
