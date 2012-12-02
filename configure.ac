dnl Process this file with autoconf to produce a configure script.
AC_INIT(portage-prefix, @version@, prefix@gentoo.org)

AC_PREREQ([2.61])

case "${prefix}" in
	'') 	AC_MSG_ERROR([bad value ${prefix} for --prefix, must not be empty]) ;;
	*/)		AC_MSG_ERROR([bad value ${prefix} for --prefix, must not end with '/']) ;;
	/*|NONE) ;;
	*) 		AC_MSG_ERROR([bad value ${prefix} for --prefix, must start with /]) ;;
esac

AC_CANONICAL_BUILD
AC_CANONICAL_HOST
AC_CANONICAL_TARGET

AM_INIT_AUTOMAKE

dnl Checks for programs.
dnl store cflags prior, otherwise it's not propagated.
if test "x$CFLAGS" != "x"
then
	CFLAGS=$CFLAGS
fi

AC_PREFIX_DEFAULT([/usr])

AC_PROG_CC
AC_PROG_INSTALL
AC_PROG_LN_S
AC_PROG_EGREP

GENTOO_PATH_XCU_ID()
GENTOO_PATH_PYTHON([2.7])

AC_PATH_PROG(PORTAGE_RM, [rm], no)
AC_PATH_PROG(PORTAGE_MV, [mv], no)
AC_PATH_PROG(PORTAGE_BASENAME, [basename], no)
AC_PATH_PROG(PORTAGE_DIRNAME, [dirname], no)
dnl avoid bash internal variable messing up things here
GENTOO_PATH_GNUPROG(PORTAGE_BASH, [bash])
GENTOO_PATH_GNUPROG(PORTAGE_SED, [sed])
GENTOO_PATH_GNUPROG(PORTAGE_WGET, [wget])
GENTOO_PATH_GNUPROG(PORTAGE_FIND, [find])
GENTOO_PATH_GNUPROG(PORTAGE_XARGS, [xargs])
GENTOO_PATH_GNUPROG(PORTAGE_GREP, [grep])

AC_ARG_WITH(portage-user,
AC_HELP_STRING([--with-portage-user=myuser],[use user 'myuser' as portage owner (default portage)]),
[case "${withval}" in
  ""|yes) AC_MSG_ERROR(bad value ${withval} for --with-portage-user);;
  *) portageuser="${withval}";;
esac],
[portageuser="portage"])

AC_ARG_WITH(portage-group,
AC_HELP_STRING([--with-portage-group=mygroup],[use group 'mygroup' as portage users group (default portage)]),
[case "${withval}" in
  ""|yes) AC_MSG_ERROR(bad value ${withval} for --with-portage-group);;
  *) portagegroup="${withval}";;
esac],
[portagegroup="portage"])

AC_ARG_WITH(root-user,
AC_HELP_STRING([--with-root-user=myuser],[uses 'myuser' as owner of installed files (default is portage-user)]),
[case "${withval}" in
  ""|yes) AC_MSG_ERROR(bad value ${withval} for --with-root-user);;
  *) rootuser="${withval}";;
esac],
[rootuser="${portageuser}"])

AC_MSG_CHECKING([for user id of ${rootuser}])
dnl grab uid of rootuser
rootuid=`${XCU_ID} -u "${rootuser}"`
if test "x`echo ${rootuid} | ${EGREP} '^[[0-9]]+$'`" != "x"
then
	AC_MSG_RESULT([${rootuid}])
else
	AC_MSG_ERROR([error finding the user id of ${rootuser}])
fi
AC_MSG_CHECKING([for group id of ${rootuser}])
rootgid=`${XCU_ID} -g "${rootuser}"`
if test "x`echo ${rootgid} | ${EGREP} '^[[0-9]]+$'`" != "x"
then
	AC_MSG_RESULT([${rootgid}])
else
	AC_MSG_ERROR([error finding the group id of ${rootuser}])
fi

AC_ARG_WITH(offset-prefix, 
AC_HELP_STRING([--with-offset-prefix],
			   [specify the installation prefix for all packages, defaults to an empty string]),
			   [PORTAGE_EPREFIX=$withval],
			   [PORTAGE_EPREFIX=''])

if test "x$PORTAGE_EPREFIX" != "x"
then
	PORTAGE_EPREFIX=`${PREFIX_PORTAGE_PYTHON} -c "import os; print os.path.normpath('$PORTAGE_EPREFIX')"`
	DEFAULT_PATH="${PORTAGE_EPREFIX}/usr/sbin:${PORTAGE_EPREFIX}/usr/bin:${PORTAGE_EPREFIX}/sbin:${PORTAGE_EPREFIX}/bin"
else
	# this is what trunk uses in ebuild.sh
	DEFAULT_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
fi

AC_ARG_WITH(extra-path, 
AC_HELP_STRING([--with-extra-path], [specify additional PATHs available to the portage build environment (use with care)]),
[EXTRA_PATH="$withval"],
[EXTRA_PATH=""])

AC_SUBST(portageuser)
AC_SUBST(portagegroup)
AC_SUBST(rootuser)
AC_SUBST(rootuid)
AC_SUBST(rootgid)
AC_SUBST(PORTAGE_EPREFIX)
AC_SUBST(DEFAULT_PATH)
AC_SUBST(EXTRA_PATH)
AC_SUBST(PORTAGE_BASE,['${exec_prefix}/lib/portage'])

AC_SUBST(PORTAGE_RM)
AC_SUBST(PORTAGE_MV)
AC_SUBST(PORTAGE_BASENAME)
AC_SUBST(PORTAGE_DIRNAME)
AC_SUBST(PORTAGE_BASH)
AC_SUBST(PORTAGE_SED)
AC_SUBST(PORTAGE_WGET)
AC_SUBST(PORTAGE_FIND)
AC_SUBST(PORTAGE_XARGS)
AC_SUBST(PORTAGE_GREP)

AC_CONFIG_FILES([subst-install], [chmod +x subst-install])
AC_CONFIG_FILES([
				 Makefile
				 man/Makefile
				 bin/Makefile
				 pym/Makefile
				 cnf/Makefile
])

AC_OUTPUT
