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

dnl GENTOO_PATH_PYTHON([minimum-version], [path])
dnl author: Fabian Groffen <grobian a gentoo.org>
AC_DEFUN([GENTOO_PATH_PYTHON],
[
  AC_PATH_PROG([PREFIX_PORTAGE_PYTHON], [python], no, $2)

  dnl is is there at all?
  if test "$PREFIX_PORTAGE_PYTHON" = "no" ; then
    AC_MSG_ERROR([no python found in your path])
  fi

  dnl is it the version we want?
  ver=`$PREFIX_PORTAGE_PYTHON -c 'import sys; print(sys.version.split(" ")[[0]])'`
  AC_MSG_CHECKING([whether $PREFIX_PORTAGE_PYTHON $ver >= $1])
  cmp=`$PREFIX_PORTAGE_PYTHON -c 'import sys; print(sys.version.split(" ")[[0]] >= "$1")'`
  if test "$cmp" = "True" ; then
    AC_MSG_RESULT([yes])
  else
    AC_MSG_ERROR([need at least version $1 of python])
  fi
])

dnl GENTOO_PATH_XCU_ID([path])
dnl author: Fabian Groffen <grobian a gentoo.org>
dnl         based on the original work by
dnl         Michael Haubenwallner <mhaubi at users dot sourceforge dot net>
AC_DEFUN([GENTOO_PATH_XCU_ID],
[
  AC_PATH_PROG([XCU_ID], [id], no, $1)

  dnl does it support all the bells and whistles we need?
  AC_MSG_CHECKING([whether $XCU_ID is good enough])
  for a in '' '-u' '-g' ; do
    if ! "$XCU_ID" $a >/dev/null 2>&1 ; then
      XCU_ID=no
      break
    fi
  done
  if test "$XCU_ID" != "no" ; then
    AC_MSG_RESULT([yes])
  else
    AC_MSG_ERROR([$XCU_ID doesn't understand $a])
  fi
])dnl

dnl GENTOO_PATH_GNUPROG([variable], [prog-to-check-for], [path])
dnl author: Fabian Groffen <grobian a gentoo.org>
AC_DEFUN([GENTOO_PATH_GNUPROG],
[
  AC_PATH_PROG([$1], [$2], no, $3)

  dnl is is there at all?
  tool="`eval echo \$$1`"
  if test "$tool" = "no" ; then
    AC_MSG_ERROR([$1 was not found in your path])
  fi

  dnl is it a GNU version?
  AC_MSG_CHECKING([whether $tool is GNU $2])
  ver=`$tool --version 2>/dev/null | head -n 1`
  case $ver in
    *GNU*)
      AC_MSG_RESULT([yes])
    ;;
    *)
      AC_MSG_ERROR([no])
    ;;
  esac
])
