dnl Process this file with autoconf to produce a configure script.
AC_INIT([portage-prefix],[@version@],[prefix@gentoo.org])

AC_PREREQ([2.71])

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

dnl avoid bash internal variable messing up things here
GENTOO_PATH_GNUPROG(PORTAGE_BASH, [bash])

AC_ARG_WITH(offset-prefix, 
AS_HELP_STRING([--with-offset-prefix],[specify the installation prefix for all packages, defaults to an empty string]),
			   [PORTAGE_EPREFIX=$withval],
			   [PORTAGE_EPREFIX=''])

if test "x$PORTAGE_EPREFIX" != "x"
then
	PORTAGE_EPREFIX=`${PREFIX_PORTAGE_PYTHON} -c "import os; print(os.path.normpath('$PORTAGE_EPREFIX'))"`
fi

AC_SUBST(PORTAGE_EPREFIX)
AC_SUBST(PORTAGE_BASE,['${exec_prefix}/lib/portage'])

AC_SUBST(PORTAGE_BASH)

AC_CONFIG_FILES([subst-install], [chmod +x subst-install])
AC_CONFIG_FILES([
				 Makefile
				 man/Makefile
				 bin/Makefile
				 lib/Makefile
				 cnf/Makefile
])

AC_OUTPUT
