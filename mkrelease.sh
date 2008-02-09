#!/bin/bash

RELEASE_BUILDDIR=${RELEASE_BUILDDIR:-/var/tmp/portage-release}
SOURCE_DIR=${RELEASE_BUILDDIR}/checkout
BRANCH=${BRANCH:-trunk}
REPOSITORY=svn+ssh://cvs.gentoo.org/var/svnroot/portage/main
SVN_LOCATION=${REPOSITORY}/${BRANCH}

die() {
	echo $@
	echo "Usage: $(basename $0) [-t|--tag] [-u|--upload <location>] <version>"
	exit 1
}

while [ "${1:1}" == "-" ]; then
	case "$1" in
		-t|--tag)
			CREATE_TAG=true
			shift
			;;
		-u|--upload)
			[ -z "$2" ] && die "missing argument to upload option"
			UPLOAD_LOCATION=${2}
			shift; shift
			;;
		*)
			die "unknown option: $1"
			;;
	esac
fi

[ -z "$1" ] && die "Need version argument"
[ -n "${1/[0-9]*}" ] && die "Invalid version argument"

VERSION=${1}
RELEASE=portage-${VERSION}
RELEASE_DIR=${RELEASE_BUILDDIR}/${RELEASE}
RELEASE_TARBALL="${RELEASE_BUILDDIR}/${RELEASE}.tar.bz2"

rm -rf "${RELEASE_DIR}" "${SOURCE_DIR}" || die "directory cleanup failed"
mkdir -p "${RELEASE_DIR}" || die "directory creation failed"


svn export "${SVN_LOCATION}" "${SOURCE_DIR}" > /dev/null || die "svn export failed"
svn2cl -o "${SOURCE_DIR}/ChangeLog" "${SVN_LOCATION}" || die "ChangeLog creation failed"

cp -a "${SOURCE_DIR}/"{bin,cnf,doc,man,pym,src} "${RELEASE_DIR}/" || die "directory copy failed"
cp "${SOURCE_DIR}/"{ChangeLog,DEVELOPING,NEWS,RELEASE-NOTES,TEST-NOTES,TODO} "${RELEASE_DIR}/" || die "file copy failed"

cd "${RELEASE_BUILDDIR}"
       
tar cfj "${RELEASE_TARBALL}" "${RELEASE}" || die "tarball creation failed"

if [ -n "${UPLOAD_LOCATION}" ]; then
	echo "uploading ${RELEASE_TARBALL} to ${UPLOAD_LOCATION}"
	scp "${RELEASE_TARBALL}" "dev.gentoo.org:${UPLOAD_LOCATION}" || die "upload failed"
else
	echo "${RELEASE_TARBALL} created"
fi

if [ -n "${CREATE_TAG}" ]; then
	echo "Tagging ${VERSION} in repository"
	svn cp ${SVN_LOCATION} ${REPOSITORY}/tags/${VERSION} || die "tagging failed"
fi

