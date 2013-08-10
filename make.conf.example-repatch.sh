#!/bin/bash

die() {
	echo "ERROR: $*" > /dev/stderr
	patch -p0 make.conf.example < make.conf.example.diff
	exit 1
}

if [[ ! -f make.conf.example || ! -f make.conf.example.x86.diff || ! -d ../.git ]]; then
	echo "ERROR: current directory is invalid" > /dev/stderr
	exit 1
fi

git diff --no-prefix --relative="$(basename "$(pwd)")" make.conf.example > make.conf.example.diff
git checkout -- make.conf.example

archs=()
for x in make.conf.example.*.diff; do
	archs+=("$(basename ${x:18} .diff)")
done


for arch in "${archs[@]}"; do
	echo "* Patching ${arch}"
	cp make.conf.example make.conf.example.${arch} || die "copy failed"
	patch -p0 make.conf.example.${arch} < make.conf.example.${arch}.diff > /dev/null || die "arch-patch failed"
	patch -p0 make.conf.example.${arch} < make.conf.example.diff > /dev/null || die "patch failed"
done

echo "* Re-patching make.conf.example"
patch -p0 make.conf.example < make.conf.example.diff > /dev/null || die "repatch failed"

for arch in "${archs[@]}"; do
	echo "* Creating diff for ${arch}"
	diff -u make.conf.example make.conf.example.${arch} > make.conf.example.${arch}.diff
	[[ -z ${KEEP_ARCH_MAKE_CONF_EXAMPLE} ]] && rm -f make.conf.example.${arch} make.conf.example.${arch}.orig
done

rm make.conf.example.diff

echo "Done"
