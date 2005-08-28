/* $Header: /var/cvsroot/gentoo-src/portage/src/sandbox/problems/Attic/libsandbox_emacsbug.c,v 1.2 2003/03/22 14:24:38 carpaski Exp $ */

#define _GNU_SOURCE
#define _REENTRANT

#define open xxx_open
#  include <dlfcn.h>
#  include <errno.h>
#  include <fcntl.h>
#  include <stdlib.h>
#  include <sys/stat.h>
#  include <sys/types.h>
#undef open

extern int open(const char*, int, mode_t);
int (*orig_open)(const char*, int, mode_t) = NULL;
int open(const char* pathname, int flags, mode_t mode)
{
	int old_errno = errno;
	
	/* code that makes xemacs' compilation produce a segfaulting executable */
/*	char** test = NULL;
	test = (char**)malloc(sizeof(char*));
	free(test);*/
	/* end of that code */

	if (!orig_open)
	{
		orig_open = dlsym(RTLD_NEXT, "open");
	}
	errno = old_errno;
	return orig_open(pathname, flags, mode);
}

