# Copyright 2015-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
#
# Compute a multilib category, as discussed here:
#
# 	https://bugs.gentoo.org/show_bug.cgi?id=534206
#
# Supported categories:
#
#	alpha_{32,64}
#	arm_{32,64}
#	hppa_{32,64}
#	ia_{32,64}
#	m68k_{32,64}
#	mips_{eabi32,eabi64,n32,n64,o32,o64}
#	ppc_{32,64}
#	riscv_{ilp32,ilp32d,lp64,lp64d}
#	s390_{32,64}
#	sh_{32,64}
#	sparc_{32,64}
#	x86_{32,64,x32}
#
# NOTES:
#
# * The ABIs referenced by some of the above *_32 and *_64 categories
#   may be imaginary, but they are listed anyway, since the goal is to
#   establish a naming convention that is as consistent and uniform as
#   possible.
#
# * The Elf header's e_ident[EI_OSABI] byte is completely ignored,
#   since OS-independence is one of the goals. The assumption is that,
#   for given installation, we are only interested in tracking multilib
#   ABIs for a single OS.

from portage.util.elf.constants import (
	EF_MIPS_ABI,
	EF_MIPS_ABI2,
	EF_RISCV_FLOAT_ABI_DOUBLE,
	EF_RISCV_RVC,
	ELFCLASS32,
	ELFCLASS64,
	EM_386, EM_68K, EM_AARCH64, EM_ALPHA, EM_ARM, EM_ALTERA_NIOS2,
	EM_IA_64, EM_MIPS,
	EM_PARISC,
	EM_PPC,
	EM_PPC64,
	EM_RISCV,
	EM_S390,
	EM_SH,
	EM_SPARC,
	EM_SPARC32PLUS, EM_SPARCV9, EM_X86_64, E_MIPS_ABI_EABI32,
	E_MIPS_ABI_EABI64, E_MIPS_ABI_O32, E_MIPS_ABI_O64)

_machine_prefix_map = {
	EM_386:             "x86",
	EM_68K:             "m68k",
	EM_AARCH64:         "arm",
	EM_ALPHA:           "alpha",
	EM_ALTERA_NIOS2:    "nios2",
	EM_ARM:             "arm",
	EM_IA_64:           "ia64",
	EM_MIPS:            "mips",
	EM_PARISC:          "hppa",
	EM_PPC:             "ppc",
	EM_PPC64:           "ppc",
	EM_RISCV:           "riscv",
	EM_S390:            "s390",
	EM_SH:              "sh",
	EM_SPARC:           "sparc",
	EM_SPARC32PLUS:     "sparc",
	EM_SPARCV9:         "sparc",
	EM_X86_64:          "x86",
}

_mips_abi_map = {
	E_MIPS_ABI_EABI32:  "eabi32",
	E_MIPS_ABI_EABI64:  "eabi64",
	E_MIPS_ABI_O32:     "o32",
	E_MIPS_ABI_O64:     "o64",
}

def _compute_suffix_mips(elf_header):

	name = None
	mips_abi = elf_header.e_flags & EF_MIPS_ABI

	if mips_abi:
		name = _mips_abi_map.get(mips_abi)
	elif elf_header.e_flags & EF_MIPS_ABI2:
		name = "n32"
	elif elf_header.ei_class == ELFCLASS64:
		name = "n64"

	return name


def _compute_suffix_riscv(elf_header):
	"""
	Compute riscv multilib suffix. In order to avoid possible
	misidentification, only the following ABIs are recognized:

		* ilp32
		* ilp32d
		* lp64
		* lp64d
	"""

	name = None

	if elf_header.ei_class == ELFCLASS64:
		if elf_header.e_flags == EF_RISCV_RVC:
			name = "lp64"
		elif elf_header.e_flags == EF_RISCV_RVC | EF_RISCV_FLOAT_ABI_DOUBLE:
			name = "lp64d"

	elif elf_header.ei_class == ELFCLASS32:
		if elf_header.e_flags == EF_RISCV_RVC:
			name = "ilp32"
		elif elf_header.e_flags == EF_RISCV_RVC | EF_RISCV_FLOAT_ABI_DOUBLE:
			name = "ilp32d"

	return name

_specialized_funcs = {
	"mips": _compute_suffix_mips,
	"riscv": _compute_suffix_riscv,
}


def compute_multilib_category(elf_header):
	"""
	Compute a multilib category from an ELF header.

	@param elf_header: an ELFHeader instance
	@type elf_header: ELFHeader
	@rtype: str
	@return: A multilib category, or None if elf_header does not fit
		into a recognized category
	"""
	category = None
	if elf_header.e_machine is not None:

		prefix = _machine_prefix_map.get(elf_header.e_machine)
		specialized_func = _specialized_funcs.get(prefix)
		suffix = None

		if specialized_func is not None:
			suffix = specialized_func(elf_header)
		elif elf_header.ei_class == ELFCLASS64:
			suffix = "64"
		elif elf_header.ei_class == ELFCLASS32:
			if elf_header.e_machine == EM_X86_64:
				suffix = "x32"
			else:
				suffix = "32"

		if prefix is None or suffix is None:
			category = None
		else:
			category = "%s_%s" % (prefix, suffix)

	return category
