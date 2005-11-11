dnl acinclude.m4 generated automatically by ac-archive's acinclude 0.5.63

dnl Copyright (C) 1994, 1995-8, 1999 Free Software Foundation, Inc.
dnl This file is free software; the Free Software Foundation
dnl gives unlimited permission to copy and/or distribute it,
dnl with or without modifications, as long as this notice is preserved.

dnl This program is distributed in the hope that it will be useful,
dnl but WITHOUT ANY WARRANTY, to the extent permitted by law; without
dnl even the implied warranty of MERCHANTABILITY or FITNESS FOR A
dnl PARTICULAR PURPOSE.

dnl ______  ______

dnl ______ /usr/share/aclocal/djmitche/ax_with_python.m4 ______
dnl @synopsis AX_WITH_PYTHON([minimum-version], [value-if-not-found], [path])
dnl 
dnl Locates an installed Python binary, placing the result in the precious
dnl variable $PYTHON.  Accepts a present $PYTHON, then --with-python, and failing
dnl that searches for python in the given path (which defaults to the system
dnl path).  If python is found, $PYTHON is set to the full path of the binary; if
dnl it is not found, $PYTHON is set to VALUE-IF-NOT-FOUND, which defaults to
dnl 'python'.
dnl 
dnl Example:
dnl
dnl   AX_WITH_PYTHON(2.2, missing)
dnl
dnl @author Dustin Mitchell <dustin@cs.uchicago.edu>
dnl @version %Id: %

AC_DEFUN([AX_WITH_PYTHON],
[
  AC_ARG_VAR([PYTHON])
 
  dnl unless PYTHON was supplied to us (as a precious variable)
  if test -z "$PYTHON"
  then
    AC_MSG_CHECKING(for --with-python)
    AC_ARG_WITH(python,
                AC_HELP_STRING([--with-python=PYTHON],
                               [absolute path name of Python executable]),
                [ if test "$withval" != "yes"
                  then
                    PYTHON="$withval"
                    AC_MSG_RESULT($withval)
                  else
                    AC_MSG_RESULT(no)
                  fi
                ],
                [ AC_MSG_RESULT(no)
                ])
  fi

  dnl if it's still not found, check the paths, or use the fallback
  if test -z "$PYTHON" 
  then
    AC_PATH_PROG([PYTHON], python, m4_ifval([$2],[$2],[python]), $3)
  fi

  dnl check version if required
  m4_ifvaln([$1], [
    dnl do this only if we didn't fall back
    if test "$PYTHON" != "m4_ifval([$2],[$2],[python])"
    then
      AC_MSG_CHECKING($PYTHON version >= $1)
      if test `$PYTHON -c ["import sys; print sys.version[:3] >= \"$1\" and \"OK\" or \"OLD\""]` = "OK"
      then
        AC_MSG_RESULT(ok)
      else
        AC_MSG_RESULT(no)
        PYTHON="$2"
      fi
    fi])
])

dnl ______ /usr/share/aclocal/Installed_Packages/ac_prog_perl_version.m4 ______
dnl @synopsis AC_PROG_PERL_VERSION(VERSION, [ACTION-IF-TRUE], [ACTION-IF-FALSE])
dnl
dnl Makes sure that perl supports the version indicated. If true the shell
dnl commands in ACTION-IF-TRUE are executed.  If not the shell commands in
dnl ACTION-IF-FALSE are run.   Note if $PERL is not set (for example by
dnl running AC_CHECK_PROG or AC_PATH_PROG), AC_CHECK_PROG(PERL, perl, perl) will
dnl be run.
dnl
dnl Example:
dnl
dnl   AC_PROG_PERL_VERSION(5.6.0)
dnl
dnl This will check to make sure that the perl you have supports at least
dnl version 5.6.0.
dnl
dnl @version %Id: ac_prog_perl_version.m4,v 1.1 2002/12/12 23:14:52 guidod Exp %
dnl @author Dean Povey <povey@wedgetail.com>
dnl
AC_DEFUN([AC_PROG_PERL_VERSION],[dnl
# Make sure we have perl
if test -z "$PERL"; then
AC_CHECK_PROG(PERL,perl,perl)
fi

# Check if version of Perl is sufficient
ac_perl_version="$1"

if test "x$PERL" != "x"; then
  AC_MSG_CHECKING(for perl version greater than or equal to $ac_perl_version)
  # NB: It would be nice to log the error if there is one, but we cannot rely
  # on autoconf internals
  $PERL -e "use $ac_perl_version;" > /dev/null 2>&1
  if test $? -ne 0; then
    AC_MSG_RESULT(no);
    $3
  else
    AC_MSG_RESULT(ok);
    $2
  fi
else
  AC_MSG_WARN(could not find perl)
fi
])dnl


dnl ______ acpackage.m4 ______
dnl @synopsis AX_PATH_XCU_ID
dnl
dnl Find the correct 'id' programm which accepts the arguments specified
dnl in http://www.opengroup.org/onlinepubs/007908799/xcu/id.html
dnl SunOS for example has this one in /usr/xpg4/bin, not /usr/bin
dnl
dnl This does AC_SUBST(XCU_ID) and accepts an absolute path
dnl to be preset in XCU_ID variable.
dnl If no id program is found, XCU_ID is left empty, not the word 'no'.
dnl
dnl Q: Why is it called 'XCU_ID' ?
dnl A: The name 'ID' might be misunderstood, so i decided 'XCU_ID'.
dnl    XCU is the section where the specification of 'id' resides in at
dnl    opengroup.org, whereof 'CU' is synonym for "commandline utilities".
dnl
dnl @version $Id$
dnl
dnl @author Michael Haubenwallner <mhaubi at users dot sourceforge dot net>
dnl
AC_DEFUN([AX_PATH_XCU_ID],[dnl
  AC_CACHE_CHECK([for a SUSv2-compatible xcu id], [ax_cv_path_XCU_ID],
  [case $XCU_ID in
  [[\\/]]* | ?:[[\\/]]*)
    # Let the user override the test with a path.
    ax_cv_path_XCU_ID="$XCU_ID"
    ;;
  *)
    save_IFS=${IFS}
    ax_cv_path_XCU_ID=no
    IFS=':'
    for p in /usr/bin:/usr/xpg4/bin:${PATH}
    do
      IFS=${save_IFS}
      test -x "${p}/id" || continue
      ax_cv_path_XCU_ID="${p}/id"
      for a in '' '-G' '-Gn' '-g' '-gn' '-gr' '-gnr' '-u' '-un' '-ur' '-unr'
      do
        "${ax_cv_path_XCU_ID}" ${a} >/dev/null 2>&1 \
        || { ax_cv_path_XCU_ID=no ; break ; }
      done
      test "x${ax_cv_path_XCU_ID}" = "xno" || break
    done
    IFS=${save_IFS}
    ;;
  esac])
  XCU_ID="${ax_cv_path_XCU_ID}"
  test "x${XCU_ID}" != "xno" || XCU_ID=
  test "$1:${XCU_ID}" != "required:"dnl
  || AC_MSG_ERROR([SUSv2-compatible id not found (use XCU_ID=/path/to/id).])
  AC_SUBST(XCU_ID)dnl
])dnl

dnl @synopsis AX_PATH_EGREP
dnl
dnl Much like AC_PROG_EGREP, but set output variable EGREP to an absolute path.
dnl
dnl Example:
dnl
dnl   AX_PATH_EGREP
dnl
dnl This let EGREP be the absolute path for egrep
dnl
dnl @version %Id:%
dnl @author Michael Haubenwallner <mhaubi at users dot sf dot net>
dnl
AC_DEFUN([AX_PATH_EGREP],[dnl
  AC_REQUIRE([AC_PROG_EGREP])dnl
  set dummy ${EGREP}
  egrep=[$]2 ; shift ; shift
  egrep_args=[$]*
  EGREP=
  AC_PATH_PROG(EGREP, [${egrep}])
  EGREP="${EGREP} ${egrep_args}"
])dnl


