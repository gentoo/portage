# data.py -- Calculated/Discovered Data Values
# Copyright 1998-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os, pwd, grp, platform
from portage.const import PORTAGE_GROUPNAME, PORTAGE_USERNAME, rootuid, EPREFIX

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.output:colorize',
	'portage.util:writemsg',
)
from portage.localization import _

ostype=platform.system()
userland = None
# Prefix always has USERLAND=GNU, even on
# FreeBSD, OpenBSD and Darwin (thank the lord!).
# Hopefully this entire USERLAND hack can go once
if EPREFIX == "" and (ostype == "DragonFly" or ostype.endswith("BSD")):
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

uid=os.getuid()
wheelgid=0

try:
	wheelgid=grp.getgrnam("wheel")[2]
except KeyError:
	pass

# The portage_uid and portage_gid global constants, and others that
# depend on them are initialized lazily, in order to allow configuration
# via make.conf. Eventually, these constants may be deprecated in favor
# of config attributes, since it's conceivable that multiple
# configurations with different constants could be used simultaneously.
_initialized_globals = set()

def _get_global(k):
	if k in _initialized_globals:
		return globals()[k]

	if k in ('portage_gid', 'portage_uid', 'secpass'):
		global portage_gid, portage_uid, secpass
		secpass = 0
		if uid == 0:
			secpass = 2
		elif portage.const.EPREFIX:
			secpass = 2
		#Discover the uid and gid of the portage user/group
		try:
			portage_gid = grp.getgrnam(_get_global('_portage_grpname')).gr_gid
		except KeyError:
			# PREFIX LOCAL: some sysadmins are insane, bug #344307
			if _get_global('_portage_grpname').isdigit():
				portage_gid = int(_get_global('_portage_grpname'))
			else:
				portage_gid = None
			# END PREFIX LOCAL
		try:
			portage_uid = pwd.getpwnam(_get_global('_portage_uname')).pw_uid
			if secpass < 1 and portage_gid in os.getgroups():
				secpass = 1
		except KeyError:
			portage_uid = None

		if portage_uid is None or portage_gid is None:
			portage_uid = 0
			portage_gid = 0
			# PREFIX LOCAL: we need to fix this one day to distinguish prefix vs non-prefix
			writemsg(colorize("BAD",
				_("portage: '%s' user or '%s' group missing." % (_get_global('_portage_uname'), _get_global('_portage_grpname')))) + "\n", noiselevel=-1)
			writemsg(colorize("BAD",
				_("         In Prefix Portage this is quite dramatic")) + "\n", noiselevel=-1)
			writemsg(colorize("BAD",
				_("         since it means you have thrown away yourself.")) + "\n", noiselevel=-1)
			writemsg(colorize("BAD",
				_("         Re-add yourself or re-bootstrap Gentoo Prefix.")) + "\n", noiselevel=-1)
			# END PREFIX LOCAL
			portage_group_warning()

		_initialized_globals.add('portage_gid')
		_initialized_globals.add('portage_uid')
		_initialized_globals.add('secpass')

		if k == 'portage_gid':
			return portage_gid
		elif k == 'portage_uid':
			return portage_uid
		elif k == 'secpass':
			return secpass
		else:
			raise AssertionError('unknown name: %s' % k)

	elif k == 'userpriv_groups':
		v = [portage_gid]
		if secpass >= 2:
			# Get a list of group IDs for the portage user. Do not use
			# grp.getgrall() since it is known to trigger spurious
			# SIGPIPE problems with nss_ldap.
			mystatus, myoutput = \
				portage.subprocess_getstatusoutput("id -G %s" % _portage_uname)
			if mystatus == os.EX_OK:
				for x in myoutput.split():
					try:
						v.append(int(x))
					except ValueError:
						pass
				v = sorted(set(v))

	elif k == '_portage_grpname':
		env = getattr(portage, 'settings', os.environ)
		# PREFIX LOCAL: use var iso hardwired 'portage'
		v = env.get('PORTAGE_GRPNAME', PORTAGE_GROUPNAME)
		# END PREFIX LOCAL
	elif k == '_portage_uname':
		env = getattr(portage, 'settings', os.environ)
		# PREFIX LOCAL: use var iso hardwired 'portage'
		v = env.get('PORTAGE_USERNAME', PORTAGE_USERNAME)
		# END PREFIX LOCAL
	else:
		raise AssertionError('unknown name: %s' % k)

	globals()[k] = v
	_initialized_globals.add(k)
	return v

class _GlobalProxy(portage.proxy.objectproxy.ObjectProxy):

	__slots__ = ('_name',)

	def __init__(self, name):
		portage.proxy.objectproxy.ObjectProxy.__init__(self)
		object.__setattr__(self, '_name', name)

	def _get_target(self):
		return _get_global(object.__getattribute__(self, '_name'))

for k in ('portage_gid', 'portage_uid', 'secpass', 'userpriv_groups',
	'_portage_grpname', '_portage_uname'):
	globals()[k] = _GlobalProxy(k)
del k

def _init(settings):
	"""
	Use config variables like PORTAGE_GRPNAME and PORTAGE_USERNAME to
	initialize global variables. This allows settings to come from make.conf
	instead of requiring them to be set in the calling environment.
	"""
	if '_portage_grpname' not in _initialized_globals:
		v = settings.get('PORTAGE_GRPNAME')
		if v is not None:
			globals()['_portage_grpname'] = v
			_initialized_globals.add('_portage_grpname')

	if '_portage_uname' not in _initialized_globals:
		v = settings.get('PORTAGE_USERNAME')
		if v is not None:
			globals()['_portage_uname'] = v
			_initialized_globals.add('_portage_uname')
