#!/usr/bin/env bash

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

if [[ -e ${DEST} ]]; then
	echo ${DEST} already exists, please remove first
	exit 1
fi

./tabcheck.py $(
	find ./ -name .git -o -name .hg -prune -o -type f ! -name '*.py' -print \
		| xargs grep -l "#\!@PREFIX_PORTAGE_PYTHON@" \
		| grep -v "^\./repoman/"
	find ./ -name .git -o -name .hg -prune -o -type f -name '*.py' -print \
		| grep -v "^\./repoman/"

)

install -d -m0755 ${DEST}
rsync -a --exclude='.git' --exclude='.hg' --exclude="repoman/" . ${DEST}
sed -i -e '/^VERSION\s*=/s/^.*$/VERSION = "'${V}-prefix'"/' \
	${DEST}/lib/portage/__init__.py
sed -i -e "/version = /s/'[^']\+'/'${V}-prefix'/" ${DEST}/setup.py
sed -i -e "1s/VERSION/${V}-prefix/" ${DEST}/man/{,ru/}*.[15]
sed -i -e "s/@version@/${V}/" ${DEST}/configure.ac

cd ${DEST}
find -name '*~' | xargs --no-run-if-empty rm -f
find -name '*.pyc' | xargs --no-run-if-empty rm -f
find -name '*.pyo' | xargs --no-run-if-empty rm -f
cd $TMP
rm -f \
	${PKG}-${V}/bin/emerge.py \
	${PKG}-${V}/bin/{pmake,sandbox} \
	${PKG}-${V}/{bin,lib}/'.#'* \
	${PKG}-${V}/{bin,lib}/*.{orig,diff} \
	${PKG}-${V}/{bin,lib}/*.py[oc]
cd $TMP/${PKG}-${V}
chmod a+x autogen.sh && ./autogen.sh || { echo "autogen failed!"; exit -1; };
rm -f autogen.sh tabcheck.py tarball.sh commit
cd $TMP
tar --numeric-owner -jcf ${TMP}/${PKG}-${V}.tar.bz2 ${PKG}-${V}
rm -R ${TMP}/${PKG}-${V}
ls -la ${TMP}/${PKG}-${V}.tar.bz2
