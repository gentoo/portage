# portage_compat_namespace.py -- provide compability layer with new namespace
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: portage_compat_namespace.py 5782 2007-01-25 17:07:32Z genone $

""" 
Special edition of portage_compat_namespace.py as for this module we can't translate
name automatically as "import portage.exec" is a SyntaxError.
"""

import sys, warnings

import portage.process
warnings.warn("DEPRECATION NOTICE: The portage_exec module was replaced by portage.process")
sys.modules["portage_exec"] = portage.process
