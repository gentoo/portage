#!/bin/bash

RELEASE_BUILDDIR=${RELEASE_BUILDDIR:-/var/tmp/portage-release}
SOURCE_DIR=${RELEASE_BUILDDIR}/checkout
BRANCH=${BRANCH:-master}
USE_TAG=false
CHANGELOG_REVISION=
UPLOAD_LOCATION=

die() {
	echo $@
	echo "Usage: ${0##*/} [--changelog-rev <tree-ish>] [-t|--tag] [-u|--upload <location>] <version>"
	exit 1
}

ARGS=$(getopt -o tu: --long changelog-rev:,tag,upload: \
	-n ${0##*/} -- "$@")
[ $? != 0 ] && die "initialization error"

eval set -- "${ARGS}"

while true; do
	case "$1" in
		--changelog-rev)
			CHANGELOG_REVISION=$2
			shift 2
			;;
		-t|--tag)
			USE_TAG=true
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
TREE_ISH=$BRANCH
if [[ $USE_TAG = true ]] ; then
	TREE_ISH=v$VERSION
fi

echo ">>> Cleaning working directories ${RELEASE_DIR} ${SOURCE_DIR}"
rm -rf "${RELEASE_DIR}" "${SOURCE_DIR}" || die "directory cleanup failed"
mkdir -p "${RELEASE_DIR}" || die "directory creation failed"
mkdir -p "$SOURCE_DIR" || die "mkdir failed"

echo ">>> Starting GIT archive"
git archive --format=tar $TREE_ISH | \
	tar -xf - -C "$SOURCE_DIR" || die "git archive failed"

echo ">>> Building release tree"
cp -a "${SOURCE_DIR}/"{bin,cnf,doc,man,misc,pym} "${RELEASE_DIR}/" || die "directory copy failed"
cp "${SOURCE_DIR}/"{DEVELOPING,LICENSE,Makefile,NEWS,RELEASE-NOTES,TEST-NOTES} \
	"${RELEASE_DIR}/" || die "file copy failed"

rm -rf "$SOURCE_DIR" || die "directory cleanup failed"

echo ">>> Setting portage.VERSION"
sed -e "s/^VERSION=.*/VERSION=\"${VERSION}\"/" \
	-i "${RELEASE_DIR}/pym/portage/__init__.py" || \
	die "Failed to patch portage.VERSION"

echo ">>> Creating Changelog"
git_log_opts=""
if [ -n "$CHANGELOG_REVISION" ] ; then
	git_log_opts+=" $CHANGELOG_REVISION^..$TREE_ISH"
else
	git_log_opts+=" $TREE_ISH"
fi
skip_next=false
git log $git_log_opts | fmt -w 80 -p "    " | while read -r ; do
	if [[ $skip_next = true ]] ; then
		skip_next=false
	elif [[ $REPLY = "    svn path="* ]] ; then
		skip_next=true
	else
		echo "$REPLY"
	fi
done > "$RELEASE_DIR/ChangeLog" || die "ChangeLog creation failed"

cd "${RELEASE_BUILDDIR}"

echo ">>> Creating release tarball ${RELEASE_TARBALL}"
tar --owner portage --group portage -cjf "${RELEASE_TARBALL}" "${RELEASE}" || \
	die "tarball creation failed"

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

exit 0
