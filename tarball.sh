#!/usr/bin/env bash
# $Id$

if [ -z "$1" ]; then
	echo
	echo "You need to have the version specified."
	echo "e.g.: $0 2.0.39-r37"
	echo
	exit 0
fi

export PKG="prefix-portage"
export TMP="/var/tmp"
export V="$1"
export DEST="${TMP}/${PKG}-${V}"

./tabcheck.py `grep "#\!@PORTAGE_PYTHON@" bin/* | cut -d: -f1` `find ./ -type f -name '*.py'`

if [ -e ${DEST} ]; then
	echo EXISTS ALREADY
	exit 1
fi

install -d -m0755 ${DEST}
rsync -a --exclude='.svn' . ${DEST}
sed -i -e '/^VERSION=/s/^.*$/VERSION="'${V}-prefix'"/' ${DEST}/pym/portage/__init__.py
sed -i -e "s/##VERSION##/${V}-prefix/g" ${DEST}/man/emerge.1
sed -i -e "s/@version@/${V}/" ${DEST}/configure.in

cd ${DEST}
find -name '*~' | xargs --no-run-if-empty rm -f
find -name '*.pyc' | xargs --no-run-if-empty rm -f
find -name '*.pyo' | xargs --no-run-if-empty rm -f
cd $TMP
rm -f ${PKG}-${V}/bin/emerge.py ${PKG}-${V}/bin/{pmake,sandbox} ${PKG}-${V}/{bin,pym}/'.#'* ${PKG}-${V}/{bin,pym}/*.{orig,diff} ${PKG}-${V}/{bin,pym}/*.py[oc]
cd $TMP/${PKG}-${V}
chmod a+x autogen.sh && ./autogen.sh || { echo "autogen failed!"; exit -1; };
rm -f autogen.sh make-man-tarball.sh tabcheck.py tarball.sh ChangeLog.000 COPYING
cd $TMP
tar -jcf ${TMP}/${PKG}-${V}.tar.bz2 ${PKG}-${V}
rm -R ${TMP}/${PKG}-${V}
ls -la ${TMP}/${PKG}-${V}.tar.bz2
