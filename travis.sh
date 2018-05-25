#!/usr/bin/env bash

# this script runs the tests as Travis would do (.travis.yml) and can be
# used to test the Prefix branch of portage on a non-Prefix system

: ${TMPDIR=/var/tmp}

HERE=$(dirname $(realpath ${BASH_SOURCE[0]}))
REPO=${HERE##*/}.$$

cd ${TMPDIR}
git clone ${HERE} ${REPO}

cd ${REPO}
printf "[build_ext]\nportage-ext-modules=true" >> setup.cfg
find . -type f -exec \
    sed -e "s|@PORTAGE_EPREFIX@||" \
		-e "s|@PORTAGE_BASE@|${PWD}|" \
        -e "s|@PORTAGE_MV@|$(type -P mv)|" \
        -e "s|@PORTAGE_BASH@|$(type -P bash)|" \
        -e "s|@PREFIX_PORTAGE_PYTHON@|$(type -P python)|" \
        -e "s|@DEFAULT_PATH@|${EPREFIX}/usr/bin:${EPREFIX}/bin|" \
        -e "s|@EXTRA_PATH@|${EPREFIX}/usr/sbin:${EPREFIX}/sbin|" \
        -e "s|@portagegroup@|$(id -gn)|" \
        -e "s|@portageuser@|$(id -un)|" \
        -e "s|@rootuser@|$(id -un)|" \
        -e "s|@rootuid@|$(id -u)|" \
        -e "s|@rootgid@|$(id -g)|" \
        -e "s|@sysconfdir@|${EPREFIX}/etc|" \
        -i '{}' +
unset EPREFIX
./setup.py test
