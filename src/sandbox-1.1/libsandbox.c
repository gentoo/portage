/*
 *  Path sandbox for the gentoo linux portage package system, initially
 *  based on the ROCK Linux Wrapper for getting a list of created files
 *
 *  to integrate with bash, bash should have been built like this
 *
 *  ./configure --prefix=<prefix> --host=<host> --without-gnu-malloc
 *
 *  it's very important that the --enable-static-link option is NOT specified
 *
 *  Copyright (C) 2001 Geert Bevin, Uwyn, http://www.uwyn.com
 *  Distributed under the terms of the GNU General Public License, v2 or later 
 *  Author : Geert Bevin <gbevin@uwyn.com>
 *
 *  Post Bevin leaving Gentoo ranks:
 *  --------------------------------
 *    Ripped out all the wrappers, and implemented those of InstallWatch.
 *    Losts of cleanups and bugfixes.  Implement a execve that forces $LIBSANDBOX
 *    in $LD_PRELOAD.  Reformat the whole thing to look  somewhat like the reworked
 *    sandbox.c from Brad House <brad@mainstreetsoftworks.com>.
 *
 *    Martin Schlemmer <azarah@gentoo.org> (18 Aug 2002)
 *
 *  Partly Copyright (C) 1998-9 Pancrazio `Ezio' de Mauro <p@demauro.net>,
 *  as some of the InstallWatch code was used.
 *
 *
 *  $Id: /var/cvsroot/gentoo-src/portage/src/sandbox-1.1/Attic/libsandbox.c,v 1.22.2.3 2004/12/01 22:14:09 carpaski Exp $
 *
 */

/* Uncomment below to enable wrapping of mknod().
 * This is broken currently. */
/* #define WRAP_MKNOD 1 */

/* Uncomment below to enable the use of strtok_r(). */
#define REENTRANT_STRTOK 1

/* Uncomment below to enable memory debugging. */
/* #define SB_MEM_DEBUG 1 */

#define open   xxx_open
#define open64 xxx_open64

/* Wrapping mknod, do not have any effect, and
 * wrapping __xmknod causes calls to it to segfault
 */
#ifdef WRAP_MKNOD
# define __xmknod xxx___xmknod
#endif

#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/param.h>
#include <unistd.h>
#include <utime.h>

#ifdef SB_MEM_DEBUG
# include <mcheck.h>
#endif

#ifdef WRAP_MKNOD
# undef __xmknod
#endif

#undef open
#undef open64

#include "localdecls.h"
#include "sandbox.h"

/* Macros to check if a function should be executed */
#define FUNCTION_SANDBOX_SAFE(func, path) \
        ((0 == is_sandbox_on()) || (1 == before_syscall(func, path)))

#define FUNCTION_SANDBOX_SAFE_INT(func, path, flags) \
        ((0 == is_sandbox_on()) || (1 == before_syscall_open_int(func, path, flags)))

#define FUNCTION_SANDBOX_SAFE_CHAR(func, path, mode) \
        ((0 == is_sandbox_on()) || (1 == before_syscall_open_char(func, path, mode)))

/* Macro to check if a wrapper is defined, if not
 * then try to resolve it again. */
#define check_dlsym(name) \
{ \
  int old_errno=errno; \
  if (!true_ ## name) true_ ## name=get_dlsym(#name); \
  errno=old_errno; \
}

/* Macro to check if we could canonicalize a path.  It returns an integer on
 * failure. */
#define canonicalize_int(path, resolved_path) \
{ \
  if (0 != canonicalize(path, resolved_path)) \
    return -1; \
}

/* Macro to check if we could canonicalize a path.  It returns a NULL pointer on
 * failure. */
#define canonicalize_ptr(path, resolved_path) \
{ \
  if (0 != canonicalize(path, resolved_path)) \
    return NULL; \
}

static char sandbox_lib[255];
//static char sandbox_pids_file[255];
static char *sandbox_pids_file;

typedef struct {
	int show_access_violation;
	char **deny_prefixes;
	int num_deny_prefixes;
	char **read_prefixes;
	int num_read_prefixes;
	char **write_prefixes;
	int num_write_prefixes;
	char **predict_prefixes;
	int num_predict_prefixes;
	char **write_denied_prefixes;
	int num_write_denied_prefixes;
} sbcontext_t;

/* glibc modified realpath() functions */
char *erealpath(const char *name, char *resolved);
/* glibc modified getcwd() functions */
char *egetcwd(char *, size_t);

static void init_wrappers(void);
static void *get_dlsym(const char *);
static int canonicalize(const char *, char *);
static int check_access(sbcontext_t *, const char *, const char *);
static int check_syscall(sbcontext_t *, const char *, const char *);
static int before_syscall(const char *, const char *);
static int before_syscall_open_int(const char *, const char *, int);
static int before_syscall_open_char(const char *, const char *, const char *);
static void clean_env_entries(char ***, int *);
static void init_context(sbcontext_t *);
static void init_env_entries(char ***, int *, char *, int);
static char *filter_path(const char *);
static int is_sandbox_on();
static int is_sandbox_pid();

/* Wrapped functions */

extern int chmod(const char *, mode_t);
static int (*true_chmod) (const char *, mode_t);
extern int chown(const char *, uid_t, gid_t);
static int (*true_chown) (const char *, uid_t, gid_t);
extern int creat(const char *, mode_t);
static int (*true_creat) (const char *, mode_t);
extern FILE *fopen(const char *, const char *);
static FILE *(*true_fopen) (const char *, const char *);
extern int lchown(const char *, uid_t, gid_t);
static int (*true_lchown) (const char *, uid_t, gid_t);
extern int link(const char *, const char *);
static int (*true_link) (const char *, const char *);
extern int mkdir(const char *, mode_t);
static int (*true_mkdir) (const char *, mode_t);
extern DIR *opendir(const char *);
static DIR *(*true_opendir) (const char *);
#ifdef WRAP_MKNOD
extern int __xmknod(const char *, mode_t, dev_t);
static int (*true___xmknod) (const char *, mode_t, dev_t);
#endif
extern int open(const char *, int, ...);
static int (*true_open) (const char *, int, ...);
extern int rename(const char *, const char *);
static int (*true_rename) (const char *, const char *);
extern int rmdir(const char *);
static int (*true_rmdir) (const char *);
extern int symlink(const char *, const char *);
static int (*true_symlink) (const char *, const char *);
extern int truncate(const char *, TRUNCATE_T);
static int (*true_truncate) (const char *, TRUNCATE_T);
extern int unlink(const char *);
static int (*true_unlink) (const char *);

#if (GLIBC_MINOR >= 1)

extern int creat64(const char *, __mode_t);
static int (*true_creat64) (const char *, __mode_t);
extern FILE *fopen64(const char *, const char *);
static FILE *(*true_fopen64) (const char *, const char *);
extern int open64(const char *, int, ...);
static int (*true_open64) (const char *, int, ...);
extern int truncate64(const char *, __off64_t);
static int (*true_truncate64) (const char *, __off64_t);

#endif

extern int execve(const char *filename, char *const argv[], char *const envp[]);
static int (*true_execve) (const char *, char *const[], char *const[]);

/*
 * Initialize the shabang
 */

static void
init_wrappers(void)
{
	void *libc_handle = NULL;

#ifdef BROKEN_RTLD_NEXT
//  printf ("RTLD_LAZY");
	libc_handle = dlopen(LIBC_VERSION, RTLD_LAZY);
#else
//  printf ("RTLD_NEXT");
	libc_handle = RTLD_NEXT;
#endif

	true_chmod = dlsym(libc_handle, "chmod");
	true_chown = dlsym(libc_handle, "chown");
	true_creat = dlsym(libc_handle, "creat");
	true_fopen = dlsym(libc_handle, "fopen");
	true_lchown = dlsym(libc_handle, "lchown");
	true_link = dlsym(libc_handle, "link");
	true_mkdir = dlsym(libc_handle, "mkdir");
	true_opendir = dlsym(libc_handle, "opendir");
#ifdef WRAP_MKNOD
	true___xmknod = dlsym(libc_handle, "__xmknod");
#endif
	true_open = dlsym(libc_handle, "open");
	true_rename = dlsym(libc_handle, "rename");
	true_rmdir = dlsym(libc_handle, "rmdir");
	true_symlink = dlsym(libc_handle, "symlink");
	true_truncate = dlsym(libc_handle, "truncate");
	true_unlink = dlsym(libc_handle, "unlink");

#if (GLIBC_MINOR >= 1)
	true_creat64 = dlsym(libc_handle, "creat64");
	true_fopen64 = dlsym(libc_handle, "fopen64");
	true_open64 = dlsym(libc_handle, "open64");
	true_truncate64 = dlsym(libc_handle, "truncate64");
#endif

	true_execve = dlsym(libc_handle, "execve");
}

void
_fini(void)
{
    free(sandbox_pids_file);
}

void
_init(void)
{
	int old_errno = errno;
	char *tmp_string = NULL;

#ifdef SB_MEM_DEBUG
	mtrace();
#endif

	init_wrappers();

	/* Get the path and name to this library */
	tmp_string = get_sandbox_lib("/");
	strncpy(sandbox_lib, tmp_string, sizeof(sandbox_lib)-1);
	if (tmp_string)
		free(tmp_string);
	tmp_string = NULL;

	/* Generate sandbox pids-file path */
	sandbox_pids_file = get_sandbox_pids_file();

	errno = old_errno;
}

static int
canonicalize(const char *path, char *resolved_path)
{
	int old_errno = errno;
	char *retval;

	*resolved_path = '\0';

	/* If path == NULL, return or we get a segfault */
	if (NULL == path) {
		errno = EINVAL;
		return -1;
	}

	/* Do not try to resolve an empty path */
	if ('\0' == path[0]) {
		errno = old_errno;
		return 0;
	}

	retval = erealpath(path, resolved_path);

	if ((!retval) && (path[0] != '/')) {
		/* The path could not be canonicalized, append it
		 * to the current working directory if it was not
		 * an absolute path
		 */
		if (errno == ENAMETOOLONG)
			return -1;

		egetcwd(resolved_path, SB_PATH_MAX - 2);
		strcat(resolved_path, "/");
		strncat(resolved_path, path, SB_PATH_MAX - 1);

		if (!erealpath(resolved_path, resolved_path)) {
			if (errno == ENAMETOOLONG) {
				/* The resolved path is too long for the buffer to hold */
				return -1;
			} else {
				/* Whatever it resolved, is not a valid path */
				errno = ENOENT;
				return -1;
			}
		}

	} else if ((!retval) && (path[0] == '/')) {
		/* Whatever it resolved, is not a valid path */
		errno = ENOENT;
		return -1;
	}

	errno = old_errno;
	return 0;
}

static void *
get_dlsym(const char *symname)
{
	void *libc_handle = NULL;
	void *symaddr = NULL;

#ifdef BROKEN_RTLD_NEXT
	libc_handle = dlopen(LIBC_VERSION, RTLD_LAZY);
	if (!libc_handle) {
		printf("libsandbox.so: Can't dlopen libc: %s\n", dlerror());
		abort();
	}
#else
	libc_handle = RTLD_NEXT;
#endif

	symaddr = dlsym(libc_handle, symname);
	if (!symaddr) {
		printf("libsandbox.so: Can't resolve %s: %s\n", symname, dlerror());
		abort();
	}

	return symaddr;
}

/*
 * Wrapper Functions
 */

int
chmod(const char *path, mode_t mode)
{
	int result = -1;
	char canonic[SB_PATH_MAX];

	canonicalize_int(path, canonic);

	if FUNCTION_SANDBOX_SAFE
		("chmod", canonic) {
		check_dlsym(chmod);
		result = true_chmod(path, mode);
		}

	return result;
}

int
chown(const char *path, uid_t owner, gid_t group)
{
	int result = -1;
	char canonic[SB_PATH_MAX];

	canonicalize_int(path, canonic);

	if FUNCTION_SANDBOX_SAFE
		("chown", canonic) {
		check_dlsym(chown);
		result = true_chown(path, owner, group);
		}

	return result;
}

int
creat(const char *pathname, mode_t mode)
{
/* Is it a system call? */
	int result = -1;
	char canonic[SB_PATH_MAX];

	canonicalize_int(pathname, canonic);

	if FUNCTION_SANDBOX_SAFE
		("creat", canonic) {
		check_dlsym(open);
		result = true_open(pathname, O_CREAT | O_WRONLY | O_TRUNC, mode);
		}

	return result;
}

FILE *
fopen(const char *pathname, const char *mode)
{
	FILE *result = NULL;
	char canonic[SB_PATH_MAX];

	canonicalize_ptr(pathname, canonic);

	if FUNCTION_SANDBOX_SAFE_CHAR
		("fopen", canonic, mode) {
		check_dlsym(fopen);
		result = true_fopen(pathname, mode);
		}

	return result;
}

int
lchown(const char *path, uid_t owner, gid_t group)
{
	int result = -1;
	char canonic[SB_PATH_MAX];

	canonicalize_int(path, canonic);

	if FUNCTION_SANDBOX_SAFE
		("lchown", canonic) {
		check_dlsym(lchown);
		result = true_lchown(path, owner, group);
		}

	return result;
}

int
link(const char *oldpath, const char *newpath)
{
	int result = -1;
	char old_canonic[SB_PATH_MAX], new_canonic[SB_PATH_MAX];

	canonicalize_int(oldpath, old_canonic);
	canonicalize_int(newpath, new_canonic);

	if FUNCTION_SANDBOX_SAFE
		("link", new_canonic) {
		check_dlsym(link);
		result = true_link(oldpath, newpath);
		}

	return result;
}

int
mkdir(const char *pathname, mode_t mode)
// returns 0 success, or -1 if an error occurred
{
	int result = -1, my_errno = errno;
	char canonic[SB_PATH_MAX];
	struct stat st;

	canonicalize_int(pathname, canonic);

	/* Check if the directory exist, return EEXIST rather than failing */
	if (0 == lstat(canonic, &st)) {
		errno = EEXIST;
		return -1; 
	}
	errno = my_errno;

	if FUNCTION_SANDBOX_SAFE
		("mkdir", canonic) {
		check_dlsym(mkdir);
		result = true_mkdir(pathname, mode);
		}

	return result;
}

DIR *
opendir(const char *name)
{
	DIR *result = NULL;
	char canonic[SB_PATH_MAX];

	canonicalize_ptr(name, canonic);

	if FUNCTION_SANDBOX_SAFE
		("opendir", canonic) {
		check_dlsym(opendir);
		result = true_opendir(name);
		}

	return result;
}

#ifdef WRAP_MKNOD

int
__xmknod(const char *pathname, mode_t mode, dev_t dev)
{
	int result = -1;
	char canonic[SB_PATH_MAX];

	canonicalize_int(pathname, canonic);

	if FUNCTION_SANDBOX_SAFE
		("__xmknod", canonic) {
		check_dlsym(__xmknod);
		result = true___xmknod(pathname, mode, dev);
		}

	return result;
}

#endif

int
open(const char *pathname, int flags, ...)
{
/* Eventually, there is a third parameter: it's mode_t mode */
	va_list ap;
	mode_t mode = 0;
	int result = -1;
	char canonic[SB_PATH_MAX];

	if (flags & O_CREAT) {
		va_start(ap, flags);
		mode = va_arg(ap, mode_t);
		va_end(ap);
	}

	canonicalize_int(pathname, canonic);

	if FUNCTION_SANDBOX_SAFE_INT
		("open", canonic, flags) {
		/* We need to resolve open() realtime in some cases,
		 * else we get a segfault when running /bin/ps, etc
		 * in a sandbox */
		check_dlsym(open);
		result = true_open(pathname, flags, mode);
		}

	return result;
}

int
rename(const char *oldpath, const char *newpath)
{
	int result = -1;
	char old_canonic[SB_PATH_MAX], new_canonic[SB_PATH_MAX];

	canonicalize_int(oldpath, old_canonic);
	canonicalize_int(newpath, new_canonic);

	if (FUNCTION_SANDBOX_SAFE("rename", old_canonic) &&
			FUNCTION_SANDBOX_SAFE("rename", new_canonic)) {
		check_dlsym(rename);
		result = true_rename(oldpath, newpath);
	}

	return result;
}

int
rmdir(const char *pathname)
{
	int result = -1;
	char canonic[SB_PATH_MAX];

	canonicalize_int(pathname, canonic);

	if FUNCTION_SANDBOX_SAFE
		("rmdir", canonic) {
		check_dlsym(rmdir);
		result = true_rmdir(pathname);
		}

	return result;
}

int
symlink(const char *oldpath, const char *newpath)
{
	int result = -1;
	char old_canonic[SB_PATH_MAX], new_canonic[SB_PATH_MAX];

	canonicalize_int(oldpath, old_canonic);
	canonicalize_int(newpath, new_canonic);

	if FUNCTION_SANDBOX_SAFE
		("symlink", new_canonic) {
		check_dlsym(symlink);
		result = true_symlink(oldpath, newpath);
		}

	return result;
}

int
truncate(const char *path, TRUNCATE_T length)
{
	int result = -1;
	char canonic[SB_PATH_MAX];

	canonicalize_int(path, canonic);

	if FUNCTION_SANDBOX_SAFE
		("truncate", canonic) {
		check_dlsym(truncate);
		result = true_truncate(path, length);
		}

	return result;
}

int
unlink(const char *pathname)
{
	int result = -1;
	char canonic[SB_PATH_MAX];

	canonicalize_int(pathname, canonic);

	if FUNCTION_SANDBOX_SAFE
		("unlink", canonic) {
		check_dlsym(unlink);
		result = true_unlink(pathname);
		}

	return result;
}

#if (GLIBC_MINOR >= 1)

int
creat64(const char *pathname, __mode_t mode)
{
/* Is it a system call? */
	int result = -1;
	char canonic[SB_PATH_MAX];

	canonicalize_int(pathname, canonic);

	if FUNCTION_SANDBOX_SAFE
		("creat64", canonic) {
		check_dlsym(open64);
		result = true_open64(pathname, O_CREAT | O_WRONLY | O_TRUNC, mode);
		}

	return result;
}

FILE *
fopen64(const char *pathname, const char *mode)
{
	FILE *result = NULL;
	char canonic[SB_PATH_MAX];

	canonicalize_ptr(pathname, canonic);

	if FUNCTION_SANDBOX_SAFE_CHAR
		("fopen64", canonic, mode) {
		check_dlsym(fopen64);
		result = true_fopen(pathname, mode);
		}

	return result;
}

int
open64(const char *pathname, int flags, ...)
{
/* Eventually, there is a third parameter: it's mode_t mode */
	va_list ap;
	mode_t mode = 0;
	int result = -1;
	char canonic[SB_PATH_MAX];

	if (flags & O_CREAT) {
		va_start(ap, flags);
		mode = va_arg(ap, mode_t);
		va_end(ap);
	}

	canonicalize_int(pathname, canonic);

	if FUNCTION_SANDBOX_SAFE_INT
		("open64", canonic, flags) {
		check_dlsym(open64);
		result = true_open64(pathname, flags, mode);
		}

	return result;
}

int
truncate64(const char *path, __off64_t length)
{
	int result = -1;
	char canonic[SB_PATH_MAX];

	canonicalize_int(path, canonic);

	if FUNCTION_SANDBOX_SAFE
		("truncate64", canonic) {
		check_dlsym(truncate64);
		result = true_truncate64(path, length);
		}

	return result;
}

#endif													/* GLIBC_MINOR >= 1 */

/*
 * Exec Wrappers
 */

int
execve(const char *filename, char *const argv[], char *const envp[])
{
	int old_errno = errno;
	int result = -1;
	int count = 0;
	int env_len = 0;
	char canonic[SB_PATH_MAX];
	char **my_env = NULL;
	int kill_env = 1;
	/* We limit the size LD_PRELOAD can be here, but it should be enough */
	char tmp_str[4096];

	canonicalize_int(filename, canonic);

	if FUNCTION_SANDBOX_SAFE
		("execve", canonic) {
		while (envp[count] != NULL) {
			if (strstr(envp[count], "LD_PRELOAD=") == envp[count]) {
				if (NULL != strstr(envp[count], sandbox_lib)) {
					my_env = (char **) envp;
					kill_env = 0;
					break;
				} else {
					int i = 0;
					const int max_envp_len =
							strlen(envp[count]) + strlen(sandbox_lib) + 1;

					/* Fail safe ... */
					if (max_envp_len > 4096) {
						fprintf(stderr, "sandbox:  max_envp_len too big!\n");
						errno = ENOMEM;
						return result;
					}

					/* Calculate envp size */
					my_env = (char **) envp;
					do
						env_len += 1;
					while (*my_env++);

					my_env = (char **) malloc((env_len + 2) * sizeof (char *));
					if (NULL == my_env) {
						errno = ENOMEM;
						return result;
					}
					/* Copy envp to my_env */
					do
						my_env[i] = envp[i];
					while (envp[i++]);

					/* Set tmp_str to envp[count] */
					strncpy(tmp_str, envp[count], max_envp_len - 1);

					/* LD_PRELOAD already have variables other than sandbox_lib,
					 * thus we have to add sandbox_lib seperated via a whitespace. */
					if (0 != strncmp(envp[count], "LD_PRELOAD=", max_envp_len - 1)) {
						strncat(tmp_str, " ", max_envp_len - strlen(tmp_str));
						strncat(tmp_str, sandbox_lib, max_envp_len - strlen(tmp_str));
					} else {
						strncat(tmp_str, sandbox_lib, max_envp_len - strlen(tmp_str));
					}

					/* Valid string? */
					tmp_str[max_envp_len] = '\0';

					/* Ok, replace my_env[count] with our version that contains
					 * sandbox_lib ... */
					my_env[count] = tmp_str;

					break;
				}
			}
			count++;
		}

		errno = old_errno;
		check_dlsym(execve);
		result = true_execve(filename, argv, my_env);
		old_errno = errno;

		if (my_env && kill_env) {
			free(my_env);
			my_env = NULL;
		}
	}

	errno = old_errno;

	return result;
}

/*
 * Internal Functions
 */

#if (GLIBC_MINOR == 1)

/* This hack is needed for glibc 2.1.1 (and others?)
 * (not really needed, but good example) */
extern int fclose(FILE *);
static int (*true_fclose) (FILE *) = NULL;
int
fclose(FILE * file)
{
	int result = -1;

	check_dlsym(fclose);
	result = true_fclose(file);

	return result;
}

#endif													/* GLIBC_MINOR == 1 */

static void
init_context(sbcontext_t * context)
{
	context->show_access_violation = 1;
	context->deny_prefixes = NULL;
	context->num_deny_prefixes = 0;
	context->read_prefixes = NULL;
	context->num_read_prefixes = 0;
	context->write_prefixes = NULL;
	context->num_write_prefixes = 0;
	context->predict_prefixes = NULL;
	context->num_predict_prefixes = 0;
	context->write_denied_prefixes = NULL;
	context->num_write_denied_prefixes = 0;
}

static int
is_sandbox_pid()
{
	int old_errno = errno;
	int result = 0;
	FILE *pids_stream = NULL;
	int pids_file = -1;
	int current_pid = 0;
	int tmp_pid = 0;

	init_wrappers();

	pids_stream = true_fopen(sandbox_pids_file, "r");

	if (NULL == pids_stream) {
		perror(">>> pids file fopen");
	} else {
		pids_file = fileno(pids_stream);

		if (pids_file < 0) {
			perror(">>> pids file fileno");
		} else {
			current_pid = getpid();

			while (EOF != fscanf(pids_stream, "%d\n", &tmp_pid)) {
				if (tmp_pid == current_pid) {
					result = 1;
					break;
				}
			}
		}
		if (EOF == fclose(pids_stream)) {
			perror(">>> pids file fclose");
		}
		pids_stream = NULL;
		pids_file = -1;
	}

	errno = old_errno;

	return result;
}

static void
clean_env_entries(char ***prefixes_array, int *prefixes_num)
{
	int old_errno = errno;
	int i = 0;

	if (NULL != *prefixes_array) {
		for (i = 0; i < *prefixes_num; i++) {
			if (NULL != (*prefixes_array)[i]) {
				free((*prefixes_array)[i]);
				(*prefixes_array)[i] = NULL;
			}
		}
		if (*prefixes_array)
			free(*prefixes_array);
		*prefixes_array = NULL;
		*prefixes_num = 0;
	}

	errno = old_errno;
}

static void
init_env_entries(char ***prefixes_array, int *prefixes_num, char *env, int warn)
{
	int old_errno = errno;
	char *prefixes_env = getenv(env);

	if (NULL == prefixes_env) {
		fprintf(stderr,
						"Sandbox error : the %s environmental variable should be defined.\n",
						env);
	} else {
		char *buffer = NULL;
		int prefixes_env_length = strlen(prefixes_env);
		int i = 0;
		int num_delimiters = 0;
		char *token = NULL;
		char *prefix = NULL;

		for (i = 0; i < prefixes_env_length; i++) {
			if (':' == prefixes_env[i]) {
				num_delimiters++;
			}
		}

		if (num_delimiters > 0) {
			*prefixes_array =
					(char **) malloc((num_delimiters + 1) * sizeof (char *));
			buffer = strndupa(prefixes_env, prefixes_env_length);

#ifdef REENTRANT_STRTOK
			token = strtok_r(buffer, ":", &buffer);
#else
			token = strtok(buffer, ":");
#endif

			while ((NULL != token) && (strlen(token) > 0)) {
				prefix = strndup(token, strlen(token));
				(*prefixes_array)[(*prefixes_num)++] = filter_path(prefix);

#ifdef REENTRANT_STRTOK
				token = strtok_r(NULL, ":", &buffer);
#else
				token = strtok(NULL, ":");
#endif

				if (prefix)
					free(prefix);
				prefix = NULL;
			}
		} else if (prefixes_env_length > 0) {
			(*prefixes_array) = (char **) malloc(sizeof (char *));

			(*prefixes_array)[(*prefixes_num)++] = filter_path(prefixes_env);
		}
	}

	errno = old_errno;
}

static char *
filter_path(const char *path)
{
	int old_errno = errno;
	char *filtered_path = (char *) malloc(SB_PATH_MAX * sizeof (char));

	canonicalize_ptr(path, filtered_path);

	errno = old_errno;

	return filtered_path;
}

static int
check_access(sbcontext_t * sbcontext, const char *func, const char *path)
{
	int old_errno = errno;
	int result = -1;
	int i = 0;
	char *filtered_path = filter_path(path);

	if ('/' != filtered_path[0]) {
		errno = old_errno;

		if (filtered_path)
			free(filtered_path);
		filtered_path = NULL;

		return 0;
	}

	if ((0 == strncmp(filtered_path, "/etc/ld.so.preload", 18))
			&& (is_sandbox_pid())) {
		result = 1;
	}

	if (-1 == result) {
		if (NULL != sbcontext->deny_prefixes) {
			for (i = 0; i < sbcontext->num_deny_prefixes; i++) {
				if (NULL != sbcontext->deny_prefixes[i]) {
					if (0 == strncmp(filtered_path,
													 sbcontext->
													 deny_prefixes[i],
													 strlen(sbcontext->deny_prefixes[i]))) {
						result = 0;
						break;
					}
				}
			}
		}

		if (-1 == result) {
			if ((NULL != sbcontext->read_prefixes) &&
					((0 == strncmp(func, "open_rd", 7)) ||
					 (0 == strncmp(func, "popen", 5)) ||
					 (0 == strncmp(func, "opendir", 7)) ||
					 (0 == strncmp(func, "system", 6)) ||
					 (0 == strncmp(func, "execl", 5)) ||
					 (0 == strncmp(func, "execlp", 6)) ||
					 (0 == strncmp(func, "execle", 6)) ||
					 (0 == strncmp(func, "execv", 5)) ||
					 (0 == strncmp(func, "execvp", 6)) ||
					 (0 == strncmp(func, "execve", 6))
					)
					) {
				for (i = 0; i < sbcontext->num_read_prefixes; i++) {
					if (NULL != sbcontext->read_prefixes[i]) {
						if (0 == strncmp(filtered_path,
														 sbcontext->
														 read_prefixes[i],
														 strlen(sbcontext->read_prefixes[i]))) {
							result = 1;
							break;
						}
					}
				}
			} else if ((NULL != sbcontext->write_prefixes) &&
								 ((0 == strncmp(func, "open_wr", 7)) ||
									(0 == strncmp(func, "creat", 5)) ||
									(0 == strncmp(func, "creat64", 7)) ||
									(0 == strncmp(func, "mkdir", 5)) ||
									(0 == strncmp(func, "mknod", 5)) ||
									(0 == strncmp(func, "mkfifo", 6)) ||
									(0 == strncmp(func, "link", 4)) ||
									(0 == strncmp(func, "symlink", 7)) ||
									(0 == strncmp(func, "rename", 6)) ||
									(0 == strncmp(func, "utime", 5)) ||
									(0 == strncmp(func, "utimes", 6)) ||
									(0 == strncmp(func, "unlink", 6)) ||
									(0 == strncmp(func, "rmdir", 5)) ||
									(0 == strncmp(func, "chown", 5)) ||
									(0 == strncmp(func, "lchown", 6)) ||
									(0 == strncmp(func, "chmod", 5)) ||
									(0 == strncmp(func, "truncate", 8)) ||
									(0 == strncmp(func, "ftruncate", 9)) ||
									(0 == strncmp(func, "truncate64", 10)) ||
									(0 == strncmp(func, "ftruncate64", 11))
								 )
					) {
				struct stat tmp_stat;

				for (i = 0; i < sbcontext->num_write_denied_prefixes; i++) {
					if (NULL != sbcontext->write_denied_prefixes[i]) {
						if (0 ==
								strncmp(filtered_path,
												sbcontext->
												write_denied_prefixes
												[i], strlen(sbcontext->write_denied_prefixes[i]))) {
							result = 0;
							break;
						}
					}
				}

				if (-1 == result) {
					for (i = 0; i < sbcontext->num_write_prefixes; i++) {
						if (NULL != sbcontext->write_prefixes[i]) {
							if (0 ==
									strncmp
									(filtered_path,
									 sbcontext->write_prefixes[i],
									 strlen(sbcontext->write_prefixes[i]))) {
								result = 1;
								break;
							}
						}
					}

					if (-1 == result) {
						/* hack to prevent mkdir of existing dirs to show errors */
						if (0 == strncmp(func, "mkdir", 5)) {
							if (0 == stat(filtered_path, &tmp_stat)) {
								sbcontext->show_access_violation = 0;
								result = 0;
							}
						}

						if (-1 == result) {
							for (i = 0; i < sbcontext->num_predict_prefixes; i++) {
								if (NULL != sbcontext->predict_prefixes[i]) {
									if (0 ==
											strncmp
											(filtered_path,
											 sbcontext->
											 predict_prefixes[i],
											 strlen(sbcontext->predict_prefixes[i]))) {
										sbcontext->show_access_violation = 0;
										result = 0;
										break;
									}
								}
							}
						}
					}
				}
			}
		}
	}

	if (-1 == result) {
		result = 0;
	}

	if (filtered_path)
		free(filtered_path);
	filtered_path = NULL;

	errno = old_errno;

	return result;
}

static int
check_syscall(sbcontext_t * sbcontext, const char *func, const char *file)
{
	int old_errno = errno;
	int result = 1;
	struct stat log_stat;
	char *log_path = NULL;
	char *absolute_path = NULL;
	char *tmp_buffer = NULL;
	int log_file = 0;
	struct stat debug_log_stat;
	char *debug_log_env = NULL;
	char *debug_log_path = NULL;
	int debug_log_file = 0;
	char buffer[512];
	char *dpath = NULL;

	init_wrappers();

	if ('/' == file[0]) {
		absolute_path = (char *) malloc((strlen(file) + 1) * sizeof (char));
		sprintf(absolute_path, "%s", file);
	} else {
		tmp_buffer = (char *) malloc(SB_PATH_MAX * sizeof (char));
		egetcwd(tmp_buffer, SB_PATH_MAX - 1);
		absolute_path = (char *) malloc((strlen(tmp_buffer) + 1 + strlen(file) + 1) * sizeof (char));
		sprintf(absolute_path, "%s/%s", tmp_buffer, file);
		if (tmp_buffer)
			free(tmp_buffer);
		tmp_buffer = NULL;
	}

	log_path = getenv("SANDBOX_LOG");
	debug_log_env = getenv("SANDBOX_DEBUG");
	debug_log_path = getenv("SANDBOX_DEBUG_LOG");

	if (((NULL == log_path) ||
			 (0 != strncmp(absolute_path, log_path, strlen(log_path)))) &&
			((NULL == debug_log_env) ||
			 (NULL == debug_log_path) ||
			 (0 != strncmp(absolute_path, debug_log_path, strlen(debug_log_path))))
			&& (0 == check_access(sbcontext, func, absolute_path))
			) {
		if (1 == sbcontext->show_access_violation) {
			fprintf(stderr,
							"\e[31;01mACCESS DENIED\033[0m  %s:%*s%s\n",
							func, (int) (10 - strlen(func)), "", absolute_path);

			if (NULL != log_path) {
				sprintf(buffer, "%s:%*s%s\n", func, (int) (10 - strlen(func)), "",
								absolute_path);
				// log_path somehow gets corrupted.  figuring out why would be good.
				dpath = strdup(log_path);
				if ((0 == lstat(log_path, &log_stat))
						&& (0 == S_ISREG(log_stat.st_mode))
						) {
					fprintf(stderr,
						"\e[31;01mSECURITY BREACH\033[0m  %s already exists and is not a regular file.\n",
						dpath);
				} else if (0 == check_access(sbcontext, "open_wr", dpath)) {
					unsetenv("SANDBOX_LOG");
					fprintf(stderr,
						"\e[31;01mSECURITY BREACH\033[0m SANDBOX_LOG %s isn't allowed via SANDBOX_WRITE\n",
						dpath);
				} else {
					log_file = true_open(dpath,
						 O_APPEND | O_WRONLY
						 | O_CREAT,
						 S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH);
					if (log_file >= 0) {
						write(log_file, buffer, strlen(buffer));
						close(log_file);
					}
				}
				free(dpath);
			}
		}

		result = 0;
	} else if (NULL != debug_log_env) {
		if (NULL != debug_log_path) {
			if (0 != strncmp(absolute_path, debug_log_path, strlen(debug_log_path))) {
				sprintf(buffer, "%s:%*s%s\n", func, (int) (10 - strlen(func)), "",
								absolute_path);
				//debug_log_path somehow gets corupted, same thing as log_path above.
				dpath = strdup(debug_log_path);
				if ((0 == lstat(debug_log_path, &debug_log_stat))
						&& (0 == S_ISREG(debug_log_stat.st_mode))
						) {
					fprintf(stderr,
						"\e[31;01mSECURITY BREACH\033[0m  %s already exists and is not a regular file.\n",
						debug_log_path);
				} else if (0 == check_access(sbcontext, "open_wr", dpath)) {
					unsetenv("SANDBOX_DEBUG");
					unsetenv("SANDBOX_DEBUG_LOG");
					fprintf(stderr,
						"\e[31;01mSECURITY BREACH\033[0m  SANDBOX_DEBUG_LOG %s isn't allowed by SANDBOX_WRITE.\n",
						dpath);
				} else {					
					debug_log_file =
						true_open(dpath,
							O_APPEND | O_WRONLY |
							O_CREAT, S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH);
					if (debug_log_file >= 0) {
						write(debug_log_file, buffer, strlen(buffer));
						close(debug_log_file);
					}
				}
				free(dpath);
			}
		} else {
			fprintf(stderr,
				"\e[32;01mACCESS ALLOWED\033[0m %s:%*s%s\n",
				func, (int) (10 - strlen(func)), "", absolute_path);
		}
	}

	if (absolute_path)
		free(absolute_path);
	absolute_path = NULL;

	errno = old_errno;

	return result;
}

static int
is_sandbox_on()
{
	int old_errno = errno;

	/* $SANDBOX_ACTIVE is an env variable that should ONLY
	 * be used internal by sandbox.c and libsanbox.c.  External
	 * sources should NEVER set it, else the sandbox is enabled
	 * in some cases when run in parallel with another sandbox,
	 * but not even in the sandbox shell.
	 *
	 * Azarah (3 Aug 2002)
	 */
	if ((NULL != getenv("SANDBOX_ON")) &&
			(0 == strncmp(getenv("SANDBOX_ON"), "1", 1)) &&
			(NULL != getenv("SANDBOX_ACTIVE")) &&
			(0 == strncmp(getenv("SANDBOX_ACTIVE"), "armedandready", 13))
			) {
		errno = old_errno;

		return 1;
	} else {
		errno = old_errno;

		return 0;
	}
}

static int
before_syscall(const char *func, const char *file)
{
	int old_errno = errno;
	int result = 1;
	sbcontext_t sbcontext;

	if (!strlen(file)) {
		/* The file/directory does not exist */
		errno = ENOENT;
		return 0;
	}

	init_context(&sbcontext);

	init_env_entries(&(sbcontext.deny_prefixes),
									 &(sbcontext.num_deny_prefixes), "SANDBOX_DENY", 1);
	init_env_entries(&(sbcontext.read_prefixes),
									 &(sbcontext.num_read_prefixes), "SANDBOX_READ", 1);
	init_env_entries(&(sbcontext.write_prefixes),
									 &(sbcontext.num_write_prefixes), "SANDBOX_WRITE", 1);
	init_env_entries(&(sbcontext.predict_prefixes),
									 &(sbcontext.num_predict_prefixes), "SANDBOX_PREDICT", 1);

	result = check_syscall(&sbcontext, func, file);

	clean_env_entries(&(sbcontext.deny_prefixes), &(sbcontext.num_deny_prefixes));
	clean_env_entries(&(sbcontext.read_prefixes), &(sbcontext.num_read_prefixes));
	clean_env_entries(&(sbcontext.write_prefixes),
										&(sbcontext.num_write_prefixes));
	clean_env_entries(&(sbcontext.predict_prefixes),
										&(sbcontext.num_predict_prefixes));

	errno = old_errno;

	if (0 == result) {
		errno = EACCES;
	}

	return result;
}

static int
before_syscall_open_int(const char *func, const char *file, int flags)
{
	if ((flags & O_WRONLY) || (flags & O_RDWR)) {
		return before_syscall("open_wr", file);
	} else {
		return before_syscall("open_rd", file);
	}
}

static int
before_syscall_open_char(const char *func, const char *file, const char *mode)
{
	if (*mode == 'r' && ((strcmp(mode, "r") == 0) ||
			     /* The strspn accept args are known non-writable modifiers */
			     (strlen(++mode) == strspn(mode, "xbtmc")))) {
		return before_syscall("open_rd", file);
	} else {
		return before_syscall("open_wr", file);
	}
}

#include "getcwd.c"
#include "canonicalize.c"

// vim:expandtab noai:cindent ai
