# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#
# These constants are available from elfutils:
# https://git.fedorahosted.org/cgit/elfutils.git/tree/libelf/elf.h

EI_CLASS           = 4
ELFCLASS32         = 1
ELFCLASS64         = 2

EI_DATA            = 5
ELFDATA2LSB        = 1
ELFDATA2MSB        = 2

E_TYPE             = 16
ET_REL             = 1
ET_EXEC            = 2
ET_DYN             = 3
ET_CORE            = 4

E_MACHINE          = 18
EM_SPARC           = 2
EM_386             = 3
EM_68K             = 4
EM_MIPS            = 8
EM_PARISC          = 15
EM_SPARC32PLUS     = 18
EM_PPC             = 20
EM_PPC64           = 21
EM_S390            = 22
EM_ARM             = 40
EM_SH              = 42
EM_SPARCV9         = 43
EM_IA_64           = 50
EM_X86_64          = 62
EM_AARCH64         = 183
EM_ALPHA           = 0x9026

E_ENTRY            = 24
EF_MIPS_ABI        = 0x0000f000
EF_MIPS_ABI2       = 0x00000020
E_MIPS_ABI_O32     = 0x00001000
E_MIPS_ABI_O64     = 0x00002000
E_MIPS_ABI_EABI32  = 0x00003000
E_MIPS_ABI_EABI64  = 0x00004000
