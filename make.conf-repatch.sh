#!/bin/bash

die() {
	echo "ERROR: $*" > /dev/stderr
	patch -p0 make.conf < make.conf.diff
	exit 1
}

if [[ ! -f make.conf || ! -f make.conf.x86.diff || ! -d ../.git ]]; then
	echo "ERROR: current directory is invalid" > /dev/stderr
	exit 1
fi

git diff --no-prefix --relative="$(basename "$(pwd)")" make.conf > make.conf.diff
git checkout -- make.conf

archs=()
for x in make.conf.*.diff; do
	archs+=("$(basename ${x:10} .diff)")
done


for arch in "${archs[@]}"; do
	echo "* Patching ${arch}"
	cp make.conf make.conf.${arch} || die "copy failed"
	patch -p0 make.conf.${arch} < make.conf.${arch}.diff > /dev/null || die "arch-patch failed"
	patch -p0 make.conf.${arch} < make.conf.diff > /dev/null || die "patch failed"
done

echo "* Re-patching make.conf"
patch -p0 make.conf < make.conf.diff > /dev/null || die "repatch failed"

for arch in "${archs[@]}"; do
	echo "* Creating diff for ${arch}"
	diff -u make.conf make.conf.${arch} > make.conf.${arch}.diff
	[[ -z ${KEEP_ARCH_MAKE_CONF} ]] && rm -f make.conf.${arch} make.conf.${arch}.orig
done

rm make.conf.diff

echo "Done"
