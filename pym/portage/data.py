# data.py -- Calculated/Discovered Data Values
# Copyright 1998-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os, pwd, grp, platform

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.output:colorize',
	'portage.util:writemsg',
)
from portage.localization import _

ostype=platform.system()
userland = None
if ostype == "DragonFly" or ostype.endswith("BSD"):
	userland = "BSD"
else:
	userland = "GNU"

lchown = getattr(os, "lchown", None)

if not lchown:
	if ostype == "Darwin":
		def lchown(*pos_args, **key_args):
			pass
	else:
		def lchown(*pargs, **kwargs):
			writemsg(colorize("BAD", "!!!") + _(
				" It seems that os.lchown does not"
				" exist.  Please rebuild python.\n"), noiselevel=-1)
		lchown()

lchown = portage._unicode_func_wrapper(lchown)

def portage_group_warning():
	warn_prefix = colorize("BAD", "*** WARNING ***  ")
	mylines = [
		"For security reasons, only system administrators should be",
		"allowed in the portage group.  Untrusted users or processes",
		"can potentially exploit the portage group for attacks such as",
		"local privilege escalation."
	]
	for x in mylines:
		writemsg(warn_prefix, noiselevel=-1)
		writemsg(x, noiselevel=-1)
		writemsg("\n", noiselevel=-1)
	writemsg("\n", noiselevel=-1)

# Portage has 3 security levels that depend on the uid and gid of the main
# process and are assigned according to the following table:
#
# Privileges  secpass  uid    gid
# normal      0        any    any
# group       1        any    portage_gid
# super       2        0      any
#
# If the "wheel" group does not exist then wheelgid falls back to 0.
# If the "portage" group does not exist then portage_uid falls back to wheelgid.

secpass=0

uid=os.getuid()
wheelgid=0

if uid==0:
	secpass=2
elif "__PORTAGE_TEST_EPREFIX" in os.environ:
	secpass = 2

try:
	wheelgid=grp.getgrnam("wheel")[2]
except KeyError:
	pass

# Allow the overriding of the user used for 'userpriv' and 'userfetch'
_portage_uname = os.environ.get('PORTAGE_USERNAME', 'portage')
_portage_grpname = os.environ.get('PORTAGE_GRPNAME', 'portage')

#Discover the uid and gid of the portage user/group
try:
	portage_uid = pwd.getpwnam(_portage_uname)[2]
	portage_gid = grp.getgrnam(_portage_grpname)[2]
	if secpass < 1 and portage_gid in os.getgroups():
		secpass=1
except KeyError:
	portage_uid=0
	portage_gid=0
	userpriv_groups = [portage_gid]
	writemsg(colorize("BAD",
		_("portage: 'portage' user or group missing.")) + "\n", noiselevel=-1)
	writemsg(_(
		"         For the defaults, line 1 goes into passwd, "
		"and 2 into group.\n"), noiselevel=-1)
	writemsg(colorize("GOOD",
		"         portage:x:250:250:portage:/var/tmp/portage:/bin/false") \
		+ "\n", noiselevel=-1)
	writemsg(colorize("GOOD", "         portage::250:portage") + "\n",
		noiselevel=-1)
	portage_group_warning()
else:
	userpriv_groups = [portage_gid]
	if secpass >= 2:
		class _LazyUserprivGroups(portage.proxy.objectproxy.ObjectProxy):
			def _get_target(self):
				global userpriv_groups
				if userpriv_groups is not self:
					return userpriv_groups
				userpriv_groups = _userpriv_groups
				# Get a list of group IDs for the portage user. Do not use
				# grp.getgrall() since it is known to trigger spurious
				# SIGPIPE problems with nss_ldap.
				mystatus, myoutput = \
					portage.subprocess_getstatusoutput("id -G %s" % _portage_uname)
				if mystatus == os.EX_OK:
					for x in myoutput.split():
						try:
							userpriv_groups.append(int(x))
						except ValueError:
							pass
					userpriv_groups[:] = sorted(set(userpriv_groups))
				return userpriv_groups

		_userpriv_groups = userpriv_groups
		userpriv_groups = _LazyUserprivGroups()
