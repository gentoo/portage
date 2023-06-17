#!/usr/bin/env bash

if [ -z "$1" ]; then
	echo
	echo "You need to have the version specified."
	echo "e.g.: $0 2.0.39-r37"
	echo
	exit 0
fi

export PKG="prefix-portage"
export TMP="/var/tmp/${PKG}-build.$$"
export V="$1"
export DEST="${TMP}/${PKG}-${V}"
export TARFILE="/var/tmp/${PKG}-${V}.tar.bz2"

# hypothetically it can exist
rm -Rf "${TMP}"

# create copy of source
install -d -m0755 "${DEST}"
rsync -a --exclude='.git' --exclude='.hg' --exclude="repoman/" . "${DEST}"

cd "${DEST}"

# expand version
sed -i -e '/^VERSION\s*=/s/^.*$/VERSION = "'${V}_prefix'"/' \
	lib/portage/__init__.py
sed -i -e "/version = /s/'[^']\+'/'${V}-prefix'/" setup.py
sed -i -e "1s/VERSION/${V}-prefix/" man/{,ru/}*.[15]
sed -i -e "s/@version@/${V}/" configure.ac

# cleanup cruft
find -name '*~' | xargs --no-run-if-empty rm -f
find -name '*.#*' | xargs --no-run-if-empty rm -f
find -name '*.pyc' | xargs --no-run-if-empty rm -f
find -name '*.pyo' | xargs --no-run-if-empty rm -f
find -name '*.orig' | xargs --no-run-if-empty rm -f
rm -Rf autom4te.cache

# we don't need these (why?)
rm -f  bin/emerge.py  bin/{pmake,sandbox}

# generate a configure file
chmod a+x autogen.sh && ./autogen.sh || { echo "autogen failed!"; exit -1; };
rm -f autogen.sh tabcheck.py tarball.sh commit

# produce final tarball
cd "${TMP}"
tar --numeric-owner -jcf "${TARFILE}" ${PKG}-${V}

cd /
rm -Rf "${TMP}"
ls -la "${TARFILE}"
