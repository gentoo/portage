/*
 * Copyright (C) 2002 Brad House <brad@mainstreetsoftworks.com>
 * Distributed under the terms of the GNU General Public License, v2 or later 
 * Author: Brad House <brad@mainstreetsoftworks.com>
 *
 * $Id: /var/cvsroot/gentoo-src/portage/src/sandbox-dev/Attic/sandbox_futils.c,v 1.3 2002/12/04 18:11:32 azarah Exp $
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

#include "sandbox.h"


char *get_sandbox_path(char *argv0)
{
  char path[255];
  char *cwd = NULL;

  /* ARGV[0] specifies full path */
  if (argv0[0] == '/') {
    strncpy(path, argv0, 254);

  /* ARGV[0] specifies relative path */
  } else {
      getcwd(cwd, 253);
      sprintf(path, "%s/%s", cwd, argv0);
      if (cwd) free(cwd);
      cwd = NULL;
  }

  /* Return just directory */
  return(sb_dirname(path));
}

char *get_sandbox_lib(char *sb_path)
{
  char path[255];

  snprintf(path, 254, "/lib/%s", LIB_NAME);
  if (file_exist(path, 0) <= 0) {
    snprintf(path, 254, "%s%s", sb_path, LIB_NAME);
  }
  return(strdup(path));
}

char *get_sandbox_rc(char *sb_path)
{
  char path[255];

  snprintf(path, 254, "/usr/lib/portage/lib/%s", BASHRC_NAME);
  if (file_exist(path, 0) <= 0) {
    snprintf(path, 254, "%s%s", sb_path, BASHRC_NAME);
  }
  return(strdup(path));
}

char *get_sandbox_log()
{
  char path[255];
  char pid_string[20];
  char *sandbox_log_env = NULL;

  sprintf(pid_string, "%d", getpid());

  strcpy(path, LOG_FILE_PREFIX);
  sandbox_log_env = getenv(ENV_SANDBOX_LOG);
  if (sandbox_log_env) {
    strcat(path, sandbox_log_env);
    strcat(path, "-");
  }
  strcat(path, pid_string);
  strcat(path, LOG_FILE_EXT);
  return(strdup(path));
}

/* Obtain base directory name. Do not allow trailing / */
char *sb_dirname(const char *path)
{
  char *ret = NULL;
  char *ptr = NULL;
  int loc = 0, i;
  int cut_len = -1;

  /* don't think NULL will ever be passed, but just in case */
  if (NULL == path) return(strdup("."));

  /* Grab pointer to last slash */
  ptr = strrchr(path, '/');
  if (NULL == ptr) {
    return(strdup("."));
  }

  /* decimal location of pointer */
  loc = ptr - path;

  /* Remove any trailing slash */
  for (i = loc-1; i >= 0; i--) {
    if (path[i] != '/') {
      cut_len = i + 1;  /* make cut_len the length of the string to keep */
      break;
    }
  }
  
  /* It could have been just a plain /, return a 1byte 0 filled string */
  if (-1 == cut_len) return(strdup(""));

  /* Allocate memory, and return the directory */
  ret = (char *)malloc((cut_len + 1) * sizeof(char));
  memcpy(ret, path, cut_len);
  ret[cut_len] = 0;

  return(ret);
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
int file_getmode(char *mode)
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
  return(mde);
}

/* Get current position in file */
long file_tell(int fp)
{
  return(lseek(fp, 0L, SEEK_CUR));
}

/* lock the file, preferrably the POSIX way */
int file_lock(int fd, int lock, char *filename)
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
    fprintf(stderr,  ">>> %s fcntl file lock: %s\n", filename, strerror(err));
    return 0;
  }
#endif
  return 1;
}

/* unlock the file, preferrably the POSIX way */
int file_unlock(int fd)
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
int file_locktype(char *mode)
{
#ifdef USE_FLOCK
  if (NULL != (strchr(mode, 'w')) || (NULL != strchr(mode, '+')) || (NULL != strchr(mode, 'a')))
    return(LOCK_EX);
  return(LOCK_SH);
#else
  if (NULL != (strchr(mode, 'w')) || (NULL != strchr(mode, '+')) || (NULL != strchr(mode, 'a')))
    return(F_WRLCK);
  return(F_RDLCK);
#endif
}

/* Use standard fopen style modes to open the specified file.  Also auto-determines and
 * locks the file either in shared or exclusive mode depending on opening mode
 */
int file_open(char *filename, char *mode, int perm_specified, ...)
{
  int fd;
  char error[250];
  va_list ap;
  int perm;

  if (perm_specified) {
    va_start(ap, perm_specified);
    perm = va_arg(ap, int);
    va_end(ap);
  }
  if (perm_specified) {
    fd = open(filename, file_getmode(mode), perm);
  } else {
    fd = open(filename, file_getmode(mode));
  }
  if (-1 == fd) {
    snprintf(error, 249, ">>> %s file mode: %s open", filename, mode);
    perror(error);
    return(fd);
  }
  /* Only lock the file if opening succeeded */
  if (-1 != fd) {
    if (0 == file_lock(fd, file_locktype(mode), filename)) {
      close(fd);
      return -1;
    }
  } else {
    snprintf(error, 249, ">>> %s file mode:%s open", filename, mode);
    perror(error);
  }
  return(fd);
}

/* Close and unlock file */
void file_close(int fd)
{
  if (-1 != fd) {
    file_unlock(fd);
    close(fd);
  }
}

/* Return length of file */
long file_length(int fd)
{
  long pos, len;
  pos = file_tell(fd);
  len = lseek(fd, 0L, SEEK_END);
  lseek(fd, pos, SEEK_SET);
  return(len);
}

/* Zero out file */
int file_truncate(int fd)
{
  lseek(fd, 0L, SEEK_SET);
  if (ftruncate(fd, 0) < 0) {
    perror(">>> file truncate");
    return 0;
  }
  return 1;
}

/* Check to see if a file exists Return: 1 success, 0 file not found, -1 error */
int file_exist(char *filename, int checkmode)
{
  struct stat mystat;

  /* Verify file exists and is regular file (not sym link) */
  if (checkmode) {
    if (-1 == lstat(filename, &mystat)) {
      /* file doesn't exist */
      if (ENOENT == errno) {
        return 0;
      } else { /* permission denied or other error */
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
      } else { /* permission denied or other error */
        perror(">>> stat file");
        return -1;
      }
    }
  }

  return 1;
}


// vim:expandtab noai:cindent ai
