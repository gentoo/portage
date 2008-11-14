#!/bin/bash

RELEASE_BUILDDIR=${RELEASE_BUILDDIR:-/var/tmp/portage-release}
SOURCE_DIR=${RELEASE_BUILDDIR}/checkout
BRANCH=${BRANCH:-trunk}
REPOSITORY=svn+ssh://cvs.gentoo.org/var/svnroot/portage/main
SVN_LOCATION=${REPOSITORY}/${BRANCH}
CHANGELOG_REVISION=""
CREATE_TAG=
CHANGELOG_REVISION=
UPLOAD_LOCATION=

die() {
	echo $@
	echo "Usage: ${0##*/} [--anon] [-t|--tag] [-u|--upload <location>] <version>"
	exit 1
}

ARGS=$(getopt -o tu: --long anon,changelog-rev:,tag,upload: \
	-n ${0##*/} -- "$@")
[ $? != 0 ] && die "initialization error"

eval set -- "${ARGS}"

while true; do
	case "$1" in
		--anon)
			REPOSITORY=svn://anonsvn.gentoo.org/portage/main
			SVN_LOCATION=${REPOSITORY}/${BRANCH}
			shift
			;;
		--changelog-rev)
			CHANGELOG_REVISION=$2
			shift 2
			;;
		-t|--tag)
			CREATE_TAG=true
			shift
			;;
		-u|--upload)
			UPLOAD_LOCATION=${2}
			shift 2
			;;
		--)
			shift
			break
			;;
		*)
			die "unknown option: $1"
			;;
	esac
done

[ -z "$1" ] && die "Need version argument"
[ -n "${1/[0-9]*}" ] && die "Invalid version argument"

VERSION=${1}
RELEASE=portage-${VERSION}
RELEASE_DIR=${RELEASE_BUILDDIR}/${RELEASE}
RELEASE_TARBALL="${RELEASE_BUILDDIR}/${RELEASE}.tar.bz2"

echo ">>> Cleaning working directories ${RELEASE_DIR} ${SOURCE_DIR}"
rm -rf "${RELEASE_DIR}" "${SOURCE_DIR}" || die "directory cleanup failed"
mkdir -p "${RELEASE_DIR}" || die "directory creation failed"

echo ">>> Starting Subversion export"
svn export "${SVN_LOCATION}" "${SOURCE_DIR}" > /dev/null || die "svn export failed"

echo ">>> Creating Changelog"
svn2cl_opts="-i --reparagraph"
[ -n $CHANGELOG_REVISION ] && svn2cl_opts+=" -r HEAD:$CHANGELOG_REVISION"
svn2cl $svn2cl_opts -o "${SOURCE_DIR}/ChangeLog" "${SVN_LOCATION}" \
	|| die "ChangeLog creation failed"

echo ">>> Building release tree"
cp -a "${SOURCE_DIR}/"{bin,cnf,doc,man,pym,src} "${RELEASE_DIR}/" || die "directory copy failed"
cp "${SOURCE_DIR}/"{ChangeLog,DEVELOPING,NEWS,RELEASE-NOTES,TEST-NOTES} \
	"${RELEASE_DIR}/" || die "file copy failed"

cd "${RELEASE_BUILDDIR}"

echo ">>> Creating release tarball ${RELEASE_TARBALL}"
tar cfj "${RELEASE_TARBALL}" "${RELEASE}" || die "tarball creation failed"

DISTDIR=$(portageq distdir)
if [ -n "${DISTDIR}" -a -d "${DISTDIR}" -a -w "${DISTDIR}" ]; then
	echo ">>> Copying release tarball into ${DISTDIR}"
	cp "${RELEASE_TARBALL}" "${DISTDIR}"/ || echo "!!! tarball copy failed"
fi

if [ -n "${UPLOAD_LOCATION}" ]; then
	echo ">>> Uploading ${RELEASE_TARBALL} to ${UPLOAD_LOCATION}"
	scp "${RELEASE_TARBALL}" "dev.gentoo.org:${UPLOAD_LOCATION}" || die "upload failed"
else
	echo "${RELEASE_TARBALL} created"
fi

if [ -n "${CREATE_TAG}" ]; then
	echo ">>> Tagging ${VERSION} in repository"
	svn cp ${SVN_LOCATION} ${REPOSITORY}/tags/${VERSION} || die "tagging failed"
fi

