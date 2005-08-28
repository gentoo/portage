/*
 * Copyright (C) 2002 Brad House <brad@mainstreetsoftworks.com>
 * Distributed under the terms of the GNU General Public License, v2 or later 
 * Author: Brad House <brad@mainstreetsoftworks.com>
 *
 * $Header: /var/cvsroot/gentoo-src/portage/src/sandbox-1.1/Attic/sandbox_futils.c,v 1.11.2.1 2004/11/03 13:12:55 ferringb Exp $
 * 
 */

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <limits.h>
#include <string.h>
#include <stdarg.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>
#include <fcntl.h>

#include <grp.h>
#include <pwd.h>

#include "sandbox.h"

/* BEGIN Prototypes */
int file_security_check(char *filename);
/* END   Prototypes */


/* glibc modified getcwd() functions */
char *egetcwd(char *, size_t);

char *
get_sandbox_path(char *argv0)
{
	char path[255];
	char *cwd = NULL;

	memset(path, 0, sizeof(path));
	/* ARGV[0] specifies full path */
	if (argv0[0] == '/') {
		strncpy(path, argv0, sizeof(path)-1);

		/* ARGV[0] specifies relative path */
	} else {
		egetcwd(cwd, sizeof(path)-2);
		snprintf(path, sizeof(path), "%s/%s", cwd, argv0);
		if (cwd)
			free(cwd);
		cwd = NULL;
	}

	/* Return just directory */
	return (sb_dirname(path));
}

char *
get_sandbox_lib(char *sb_path)
{
	char path[255];

#ifdef SB_HAVE_64BIT_ARCH
        snprintf(path, sizeof(path), "%s", LIB_NAME);
#else
	snprintf(path, sizeof(path), "/lib/%s", LIB_NAME);
	if (file_exist(path, 0) <= 0) {
		snprintf(path, sizeof(path), "%s%s", sb_path, LIB_NAME);
	}
#endif
	return (strdup(path));
}

char *
get_sandbox_pids_file(void)
{
	if (0 < getenv("SANDBOX_PIDS_FILE")) {
		return (strdup(getenv("SANDBOX_PIDS_FILE")));
	}
	return (strdup(PIDS_FILE));
}

char *
get_sandbox_rc(char *sb_path)
{
	char path[255];

	snprintf(path, sizeof(path), "/usr/lib/portage/lib/%s", BASHRC_NAME);
	if (file_exist(path, 0) <= 0) {
		snprintf(path, sizeof(path), "%s%s", sb_path, BASHRC_NAME);
	}
	return (strdup(path));
}

char *
get_sandbox_log()
{
	char path[255];
	char *sandbox_log_env = NULL;

	/* THIS CHUNK BREAK THINGS BY DOING THIS:
	 * SANDBOX_LOG=/tmp/sandbox-app-admin/superadduser-1.0.7-11063.log
	 */

	sandbox_log_env = getenv(ENV_SANDBOX_LOG);
	snprintf(path, sizeof(path)-1, "%s%s%s%d%s", LOG_FILE_PREFIX,
		( sandbox_log_env == NULL ? "" : sandbox_log_env ),
		( sandbox_log_env == NULL ? "" : "-" ),
		getpid(), LOG_FILE_EXT);
	return (strdup(path));
}

/* Obtain base directory name. Do not allow trailing / */
char *
sb_dirname(const char *path)
{
	char *ret = NULL;
	char *ptr = NULL;
	int loc = 0, i;
	int cut_len = -1;

	/* don't think NULL will ever be passed, but just in case */
	if (NULL == path)
		return (strdup("."));

	/* Grab pointer to last slash */
	ptr = strrchr(path, '/');
	if (NULL == ptr) {
		return (strdup("."));
	}

	/* decimal location of pointer */
	loc = ptr - path;

	/* Remove any trailing slash */
	for (i = loc - 1; i >= 0; i--) {
		if (path[i] != '/') {
			cut_len = i + 1;					/* make cut_len the length of the string to keep */
			break;
		}
	}

	/* It could have been just a plain /, return a 1byte 0 filled string */
	if (-1 == cut_len)
		return (strdup(""));

	/* Allocate memory, and return the directory */
	ret = (char *) malloc((cut_len + 1) * sizeof (char));
	memcpy(ret, path, cut_len);
	ret[cut_len] = 0;

	return (ret);
}

/*
char* dirname(const char* path)
{
  char* base = NULL;
  unsigned int length = 0;

  base = strrchr(path, '/');
  if (NULL == base)
  {
    return strdup(".");
  }
  while (base > path && *base == '/')
  {
    base--;
  }
  length = (unsigned int) 1 + base - path;

  base = malloc(sizeof(char)*(length+1));
  memmove(base, path, length);
  base[length] = 0;

  return base;
}*/

/* Convert text (string) modes to integer values */
int
file_getmode(char *mode)
{
	int mde = 0;
	if (0 == strcasecmp(mode, "r+")) {
		mde = O_RDWR | O_CREAT;
	} else if (0 == strcasecmp(mode, "w+")) {
		mde = O_RDWR | O_CREAT | O_TRUNC;
	} else if (0 == strcasecmp(mode, "a+")) {
		mde = O_RDWR | O_CREAT | O_APPEND;
	} else if (0 == strcasecmp(mode, "r")) {
		mde = O_RDONLY;
	} else if (0 == strcasecmp(mode, "w")) {
		mde = O_WRONLY | O_CREAT | O_TRUNC;
	} else if (0 == strcasecmp(mode, "a")) {
		mde = O_WRONLY | O_APPEND | O_CREAT;
	} else {
		mde = O_RDONLY;
	}
	return (mde);
}

/* Get current position in file */
long
file_tell(int fp)
{
	return (lseek(fp, 0L, SEEK_CUR));
}

/* lock the file, preferrably the POSIX way */
int
file_lock(int fd, int lock, char *filename)
{
	int err;
#ifdef USE_FLOCK
	if (flock(fd, lock) < 0) {
		err = errno;
		fprintf(stderr, ">>> %s flock file lock: %s\n", filename, strerror(err));
		return 0;
	}
#else
	struct flock fl;
	fl.l_type = lock;
	fl.l_whence = SEEK_SET;
	fl.l_start = 0L;
	fl.l_len = 0L;
	fl.l_pid = getpid();
	if (fcntl(fd, F_SETLKW, &fl) < 0) {
		err = errno;
		fprintf(stderr, ">>> %s fcntl file lock: %s\n", filename, strerror(err));
		return 0;
	}
#endif
	return 1;
}

/* unlock the file, preferrably the POSIX way */
int
file_unlock(int fd)
{
#ifdef USE_FLOCK
	if (flock(fd, LOCK_UN) < 0) {
		perror(">>> flock file unlock");
		return 0;
	}
#else
	struct flock fl;
	fl.l_type = F_UNLCK;
	fl.l_whence = SEEK_SET;
	fl.l_start = 0L;
	fl.l_len = 0L;
	fl.l_pid = getpid();
	if (fcntl(fd, F_SETLKW, &fl) < 0) {
		perror(">>> fcntl file unlock");
		return 0;
	}
#endif
	return 1;
}

/* Auto-determine from how the file was opened, what kind of lock to lock
 * the file with
 */
int
file_locktype(char *mode)
{
#ifdef USE_FLOCK
	if (NULL != (strchr(mode, 'w')) || (NULL != strchr(mode, '+'))
			|| (NULL != strchr(mode, 'a')))
		return (LOCK_EX);
	return (LOCK_SH);
#else
	if (NULL != (strchr(mode, 'w')) || (NULL != strchr(mode, '+'))
			|| (NULL != strchr(mode, 'a')))
		return (F_WRLCK);
	return (F_RDLCK);
#endif
}

/* Use standard fopen style modes to open the specified file.  Also auto-determines and
 * locks the file either in shared or exclusive mode depending on opening mode
 */
int
file_open(char *filename, char *mode, int perm_specified, ...)
{
	int fd;
	char error[250];
	va_list ap;
	int perm;
	char *group = NULL;
	struct group *group_struct;
	
	file_security_check(filename);

	if (perm_specified) {
		va_start(ap, perm_specified);
		perm = va_arg(ap, int);
		group = va_arg(ap, char *);
		va_end(ap);
	}
	fd = open(filename, file_getmode(mode));
	file_security_check(filename);
	if (-1 == fd) {
		snprintf(error, sizeof(error), ">>> %s file mode: %s open", filename, mode);
		perror(error);
		return (fd);
	}
	if (perm_specified) {
		if (fchmod(fd, 0664) && (0 == getuid())) {
			snprintf(error, sizeof(error), ">>> Could not set mode: %s", filename);
			perror(error);
		}
	}
	if (NULL != group) {
		group_struct = getgrnam(group);
		if (NULL == group) {
			snprintf(error, sizeof(error), ">>> Could not get grp number: %s", group);
			perror(error);
		} else {
			if (fchown(fd, -1, group_struct->gr_gid) && (0 == getuid())) {
				snprintf(error, sizeof(error), ">>> Could not set group: %s", filename);
				perror(error);
			}
		}
	}
	/* Only lock the file if opening succeeded */
	if (-1 != fd) {
		if(file_security_check(filename) != 0) {
		  /* Security violation occured between the last check and the     */
			/* creation of the file. As SpanKY pointed out there is a race   */
			/* condition here, so if there is a problem here we'll mesg and  */
			/* bail out to avoid it until we can work and test a better fix. */
			fprintf(stderr, "\n\nSECURITY RACE CONDITION: Problem recurred after creation!\nBAILING OUT\n\n");
			exit(127);
		}

		if (0 == file_lock(fd, file_locktype(mode), filename)) {
			close(fd);
			return -1;
		}
	} else {
		snprintf(error, sizeof(error), ">>> %s file mode:%s open", filename, mode);
		perror(error);
	}
	return (fd);
}

/* Close and unlock file */
void
file_close(int fd)
{
	if (-1 != fd) {
		file_unlock(fd);
		close(fd);
	}
}

/* Return length of file */
long
file_length(int fd)
{
	long pos, len;
	pos = file_tell(fd);
	len = lseek(fd, 0L, SEEK_END);
	lseek(fd, pos, SEEK_SET);
	return (len);
}

/* Zero out file */
int
file_truncate(int fd)
{
	lseek(fd, 0L, SEEK_SET);
	if (ftruncate(fd, 0) < 0) {
		perror(">>> file truncate");
		return 0;
	}
	return 1;
}

/* Check to see if a file exists Return: 1 success, 0 file not found, -1 error */
int
file_exist(char *filename, int checkmode)
{
	struct stat mystat;

	/* Verify file exists and is regular file (not sym link) */
	if (checkmode) {
		if (-1 == lstat(filename, &mystat)) {
			/* file doesn't exist */
			if (ENOENT == errno) {
				return 0;
			} else {									/* permission denied or other error */
				perror(">>> stat file");
				return -1;
			}
		}
		if (!S_ISREG(mystat.st_mode))
			return -1;

		/* Just plain verify the file exists */
	} else {
		if (-1 == stat(filename, &mystat)) {
			/* file does not exist */
			if (ENOENT == errno) {
				return 0;
			} else {									/* permission denied or other error */
				perror(">>> stat file");
				return -1;
			}
		}
	}

	return 1;
}

int file_security_check(char *filename) { /* 0 == fine, >0 == problem */
	struct stat stat_buf;
	struct group *group_buf;
	struct passwd *passwd_buf;
	
	passwd_buf = getpwnam("portage");
	group_buf = getgrnam("portage");

	if((lstat(filename, &stat_buf) == -1) && (errno == ENOENT)) {
		/* Doesn't exist. */
		return 0;
	}
	else {
		if((stat_buf.st_nlink) > 1) { /* Security: We are handlinked... */
			if(unlink(filename)) {
				fprintf(stderr,
				   "Unable to delete file in security violation (hardlinked): %s\n",
					 filename);
				exit(127);
			}
			fprintf(stderr,
			   "File in security violation (hardlinked): %s\n",
				 filename);
			return 1;
		}
		else if(S_ISLNK(stat_buf.st_mode)) { /* Security: We are a symlink? */
			fprintf(stderr,
			   "File in security violation (symlink): %s\n",
				 filename);
			exit(127);
		}
		else if(0 == S_ISREG(stat_buf.st_mode)) { /* Security: special file */
			fprintf(stderr,
			   "File in security violation (not regular): %s\n",
				 filename);
			exit(127);
		}
		else if(stat_buf.st_mode & S_IWOTH) { /* Security: We are o+w? */
			if(unlink(filename)) {
				fprintf(stderr,
				   "Unable to delete file in security violation (world write): %s\n",
					 filename);
				exit(127);
			}
			fprintf(stderr,
			   "File in security violation (world write): %s\n",
				 filename);
			return 1;
		}
		else if(
		   !((stat_buf.st_uid == 0) || (stat_buf.st_uid == getuid()) || ((passwd_buf!=NULL) && (stat_buf.st_uid == passwd_buf->pw_uid))) ||
			 !((stat_buf.st_gid == 0) || (stat_buf.st_gid == getgid()) || ((group_buf !=NULL) && (stat_buf.st_gid == group_buf->gr_gid)))
			 ) { /* Security: Owner/Group isn't right. */
			 
			/* uid = 0 or myuid or portage */
			/* gid = 0 or mygid or portage */
			
			if(0) {
				fprintf(stderr, "--1: %d,%d,%d,%d\n--2: %d,%d,%d,%d\n",

					(stat_buf.st_uid == 0),
					(stat_buf.st_uid == getuid()),
					(passwd_buf!=NULL),
					(passwd_buf!=NULL)? (stat_buf.st_uid == passwd_buf->pw_uid) : -1,

				  (stat_buf.st_gid == 0),
					(stat_buf.st_gid == getgid()),
					(group_buf !=NULL),
					(group_buf !=NULL)? (stat_buf.st_gid == group_buf->gr_gid) : -1);
			}
			
			/* manpage: "The return value may point to static area" */
			/* DO NOT ACTUALLY FREE THIS... It'll segfault.         */
			/* if(passwd_buf != NULL) { free(passwd_buf); }         */
			/* if(group_buf  != NULL) { free(group_buf); }          */
				 
			if(unlink(filename)) {
				fprintf(stderr,
				   "Unable to delete file in security violation (bad owner/group): %s\n",
					 filename);
				exit(127);
			}
			fprintf(stderr,
			   "File in security violation (bad owner/group): %s\n",
				 filename);
			return 1;
		}
	} /* Stat */
	return 0;
}

// vim:expandtab noai:cindent ai
