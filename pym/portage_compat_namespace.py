# portage_compat_namespace.py -- provide compability layer with new namespace
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

""" 
This module checks the name under which it is imported and attempts to load
the corresponding module of the new portage namespace, inserting it into the
loaded modules list.
It also issues a warning to the caller to migrate to the new namespace.
Note that this module should never be used with it's true name, but only by 
links pointing to it. Also it is limited to portage_foo -> portage.foo 
translations, however existing subpackages shouldn't use it anyway to maintain 
compability with 3rd party modules (like elog or cache plugins), and they 
shouldn't be directly imported by external consumers.

This module is based on an idea by Brian Harring.
"""

import sys, warnings

__oldname = __name__
if __name__.startswith("portage_"):
	__newname = __name__.replace("_", ".")
else:
	__newname = "portage."+__name__

try:
	__package = __import__(__newname, globals(), locals())
	__realmodule = getattr(__package, __newname[8:])
except ImportError, AttributeError:
	raise ImportError("No module named %s" % __oldname)

warnings.warn("DEPRECATION NOTICE: The %s module was replaced by %s" % (__oldname, __newname))
sys.modules[__oldname] = __realmodule
