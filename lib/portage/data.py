# data.py -- Calculated/Discovered Data Values
# Copyright 1998-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import grp
import os
import platform
import pwd

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.output:colorize',
	'portage.util:writemsg',
	'portage.util.path:first_existing',
	'subprocess'
)
from portage.localization import _

ostype = platform.system()
userland = None
if ostype == "DragonFly" or ostype.endswith("BSD"):
	userland = "BSD"
else:
	userland = "GNU"

lchown = getattr(os, "lchown", None)

if not lchown:
	if ostype == "Darwin":
		def lchown(*_args, **_kwargs):
			pass
	else:
		def lchown(*_args, **_kwargs):
			writemsg(colorize("BAD", "!!!") + _(
				" It seems that os.lchown does not"
				" exist.  Please rebuild python.\n"), noiselevel=-1)
		lchown()

lchown = portage._unicode_func_wrapper(lchown)

def _target_eprefix():
	"""
	Calculate the target EPREFIX, which may be different from
	portage.const.EPREFIX due to cross-prefix support. The result
	is equivalent to portage.settings["EPREFIX"], but the calculation
	is done without the expense of instantiating portage.settings.
	@rtype: str
	@return: the target EPREFIX
	"""
	eprefix = os.environ.get("EPREFIX", portage.const.EPREFIX)
	if eprefix:
		eprefix = portage.util.normalize_path(eprefix)
	return eprefix

def _target_root():
	"""
	Calculate the target ROOT. The result is equivalent to
	portage.settings["ROOT"], but the calculation
	is done without the expense of instantiating portage.settings.
	@rtype: str
	@return: the target ROOT (always ends with a slash)
	"""
	root = os.environ.get("ROOT")
	if not root:
		# Handle either empty or unset ROOT.
		root = os.sep
	root = portage.util.normalize_path(root)
	return root.rstrip(os.sep) + os.sep

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

# If the current user is not root, but has write access to the
# EROOT directory (not due to the 0002 bit), then use "unprivileged"
# mode which sets secpass = 2 and uses the UID and GID of the EROOT
# directory to generate default PORTAGE_INST_GID, PORTAGE_INST_UID,
# PORTAGE_USERNAME, and PORTAGE_GRPNAME settings.
def _unprivileged_mode(eroot, eroot_st):
	return os.getuid() != 0 and os.access(eroot, os.W_OK) and \
		not eroot_st.st_mode & 0o0002

uid = os.getuid()
wheelgid = 0
try:
	wheelgid = grp.getgrnam("wheel")[2]
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

	if k == 'secpass':

		unprivileged = False
		if hasattr(portage, 'settings'):
			unprivileged = "unprivileged" in portage.settings.features
		else:
			# The config class has equivalent code, but we also need to
			# do it here if _disable_legacy_globals() has been called.
			eroot_or_parent = first_existing(os.path.join(
				_target_root(), _target_eprefix().lstrip(os.sep)))
			try:
				eroot_st = os.stat(eroot_or_parent)
			except OSError:
				pass
			else:
				unprivileged = _unprivileged_mode(
					eroot_or_parent, eroot_st)

		v = 0
		if uid == 0:
			v = 2
		elif unprivileged:
			v = 2
		elif _get_global('portage_gid') in os.getgroups():
			v = 1

	elif k in ('portage_gid', 'portage_uid'):

		#Discover the uid and gid of the portage user/group
		keyerror = False
		try:
			portage_uid = pwd.getpwnam(_get_global('_portage_username')).pw_uid
		except KeyError:
			keyerror = True
			portage_uid = 0

		try:
			portage_gid = grp.getgrnam(_get_global('_portage_grpname')).gr_gid
		except KeyError:
			keyerror = True
			portage_gid = 0

		# Suppress this error message if both PORTAGE_GRPNAME and
		# PORTAGE_USERNAME are set to "root", for things like
		# Android (see bug #454060).
		if keyerror and not (_get_global('_portage_username') == "root" and
			_get_global('_portage_grpname') == "root"):
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

		globals()['portage_gid'] = portage_gid
		_initialized_globals.add('portage_gid')
		globals()['portage_uid'] = portage_uid
		_initialized_globals.add('portage_uid')

		if k == 'portage_gid':
			return portage_gid
		if k == 'portage_uid':
			return portage_uid
		raise AssertionError('unknown name: %s' % k)

	elif k == 'userpriv_groups':
		v = [_get_global('portage_gid')]
		if secpass >= 2:
			# Get a list of group IDs for the portage user. Do not use
			# grp.getgrall() since it is known to trigger spurious
			# SIGPIPE problems with nss_ldap.
			cmd = ["id", "-G", _portage_username]

			encoding = portage._encodings['content']
			cmd = [portage._unicode_encode(x,
				encoding=encoding, errors='strict') for x in cmd]
			proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT)
			myoutput = proc.communicate()[0]
			status = proc.wait()
			if os.WIFEXITED(status) and os.WEXITSTATUS(status) == os.EX_OK:
				for x in portage._unicode_decode(myoutput,
					encoding=encoding, errors='strict').split():
					try:
						v.append(int(x))
					except ValueError:
						pass
				v = sorted(set(v))

	# Avoid instantiating portage.settings when the desired
	# variable is set in os.environ.
	elif k in ('_portage_grpname', '_portage_username'):
		v = None
		if k == '_portage_grpname':
			env_key = 'PORTAGE_GRPNAME'
		else:
			env_key = 'PORTAGE_USERNAME'

		if env_key in os.environ:
			v = os.environ[env_key]
		elif hasattr(portage, 'settings'):
			v = portage.settings.get(env_key)
		else:
			# The config class has equivalent code, but we also need to
			# do it here if _disable_legacy_globals() has been called.
			eroot_or_parent = first_existing(os.path.join(
				_target_root(), _target_eprefix().lstrip(os.sep)))
			try:
				eroot_st = os.stat(eroot_or_parent)
			except OSError:
				pass
			else:
				if _unprivileged_mode(eroot_or_parent, eroot_st):
					if k == '_portage_grpname':
						try:
							grp_struct = grp.getgrgid(eroot_st.st_gid)
						except KeyError:
							pass
						else:
							v = grp_struct.gr_name
					else:
						try:
							pwd_struct = pwd.getpwuid(eroot_st.st_uid)
						except KeyError:
							pass
						else:
							v = pwd_struct.pw_name

		if v is None:
			v = 'portage'
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
	'_portage_grpname', '_portage_username'):
	globals()[k] = _GlobalProxy(k)
del k

def _init(settings):
	"""
	Use config variables like PORTAGE_GRPNAME and PORTAGE_USERNAME to
	initialize global variables. This allows settings to come from make.conf
	instead of requiring them to be set in the calling environment.
	"""
	if '_portage_grpname' not in _initialized_globals and \
		'_portage_username' not in _initialized_globals:

		# Prevents "TypeError: expected string" errors
		# from grp.getgrnam() with PyPy
		native_string = platform.python_implementation() == 'PyPy'

		v = settings.get('PORTAGE_GRPNAME', 'portage')
		if native_string:
			v = portage._native_string(v)
		globals()['_portage_grpname'] = v
		_initialized_globals.add('_portage_grpname')

		v = settings.get('PORTAGE_USERNAME', 'portage')
		if native_string:
			v = portage._native_string(v)
		globals()['_portage_username'] = v
		_initialized_globals.add('_portage_username')

	if 'secpass' not in _initialized_globals:
		v = 0
		if uid == 0:
			v = 2
		elif "unprivileged" in settings.features:
			v = 2
		elif portage_gid in os.getgroups():
			v = 1
		globals()['secpass'] = v
		_initialized_globals.add('secpass')
