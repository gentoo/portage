#!/bin/bash
# $Id: /var/cvsroot/gentoo-src/portage/Attic/tarball.sh,v 1.181.2.2 2005/05/01 16:04:51 jstubbs Exp $

if [ -z "$1" ]; then
	echo
	echo "You need to have the version specified."
	echo "e.g.: $0 2.0.39-r37"
	echo
	exit 0
fi

export PKG="portage-prefix"
export TMP="/tmp"
export V="$1"
export DEST="${TMP}/${PKG}-${V}"
export PREVEB="2.0.49_pre2"

./tabcheck.py bin/emerge `find ./ -type f -name '*.py'`

if [ -e $TMP/${PKG}-${V} ]; then
	echo EXISTS ALREADY
	exit 1
fi

rm -rf ${DEST}
install -d -m0755 ${DEST}
cp -pPR . ${DEST}
cp ${DEST}/pym/portage.py ${DEST}/pym/portage.py.orig
sed '/^VERSION=/s/^.*$/VERSION="'${V}'"/' < ${DEST}/pym/portage.py.orig > ${DEST}/pym/portage.py
cp ${DEST}/man/emerge.1 ${DEST}/man/emerge.1.orig
sed "s/##VERSION##/${V}/g" < ${DEST}/man/emerge.1.orig > ${DEST}/man/emerge.1
rm ${DEST}/pym/portage.py.orig ${DEST}/man/emerge.1.orig
rm ${DEST}/man/*.eclass.5

sed -i -e "s:\t:  :g" ChangeLog
cp ChangeLog ${DEST}

cd ${DEST}
find -name CVS -exec rm -rf {} \;
find -name '.svn' -type d -exec rm -rf {} \;
find -name '*~' -exec rm -rf {} \;
find -name '*.pyc' -exec rm -rf {} \;
find -name '*.pyo' -exec rm -rf {} \;
chown -R root:0 ${DEST}
cd $TMP
rm -f ${PKG}-${V}/bin/emerge.py ${PKG}-${V}/bin/{pmake,sandbox} ${PKG}-${V}/{bin,pym}/'.#'* ${PKG}-${V}/{bin,pym}/*.{orig,diff} ${PKG}-${V}/{bin,pym}/*.py[oc]
cd $TMP/${PKG}-${V}
chmod a+x autogen.sh && ./autogen.sh
rm -f AUTHORS NEWS autogen.sh make-man-tarball.sh tabcheck.py tarball.sh ChangeLog.000 COPYING
cd $TMP
tar cjvf ${TMP}/${PKG}-${V}.tar.bz2 ${PKG}-${V}
scp ${TMP}/${PKG}-${V}.tar.bz2 kito@dev.gentoo.org:~/public_html/distfiles/ 
