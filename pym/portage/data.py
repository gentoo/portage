# data.py -- Calculated/Discovered Data Values
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os, sys, pwd, grp
from portage.util import writemsg
from portage.const import rootuid, portageuser, portagegroup
from portage.output import green,red
from portage.output import create_color_func
bad = create_color_func("BAD")

ostype=os.uname()[0]

userland = None
lchown = getattr(os, "lchown", None)
os.environ.setdefault("XARGS", "xargs -r")
os.environ["XARGS"]="xargs -r"

# "fix" for lchown on Darwin
if ostype == "Darwin":
	def lchown(*pos_args, **key_args):
		pass

if not lchown:
	if "lchown" in dir(os):
		# Included in python-2.3
		lchown = os.lchown
	else:
		try:
			import missingos
			lchown = missingos.lchown
		except ImportError:
			def lchown(*pos_args, **key_args):
				writemsg(red("!!!") + " It seems that os.lchown does not" + \
					" exist.  Please rebuild python.\n", noiselevel=-1)
			lchown()

def portage_group_warning():
	warn_prefix = bad("*** WARNING ***  ")
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

if uid==rootuid:
	secpass=2
try:
	wheelgid=grp.getgrnam("wheel")[2]
except KeyError:
	pass

#Discover the uid and gid of the portage user/group
try:
	portage_uid=pwd.getpwnam(portageuser)[2]
	portage_gid=grp.getgrnam(portagegroup)[2]
	if secpass < 1 and portage_gid in os.getgroups():
		secpass=1
except KeyError:
	portage_uid=0
	portage_gid=0
	writemsg("\n")
	writemsg(  red("portage: "+portageuser+" user or "+portagegroup+" group missing.\n"))
	writemsg(  red("         In Prefix Portage this is quite dramatic\n"))
	writemsg(  red("         since it means you have thrown away yourself.\n"))
	writemsg(      "         Re-add yourself or re-bootstrap Gentoo Prefix.\n")
	writemsg("\n")
	portage_group_warning()

userpriv_groups = [portage_gid]
if secpass >= 2:
	# Get a list of group IDs for the portage user.  Do not use grp.getgrall()
	# since it is known to trigger spurious SIGPIPE problems with nss_ldap.
	from commands import getstatusoutput
	mystatus, myoutput = getstatusoutput("id -G " + portageuser)
	if mystatus == os.EX_OK:
		for x in myoutput.split():
			try:
				userpriv_groups.append(int(x))
			except ValueError:
				pass
			del x
		userpriv_groups = list(set(userpriv_groups))
	del getstatusoutput, mystatus, myoutput
