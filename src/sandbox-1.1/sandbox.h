/* 
 * Copyright (C) 2002 Brad House <brad@mainstreetsoftworks.com>,
 * Possibly based on code from Geert Bevin, Uwyn, http://www.uwyn.com
 * Distributed under the terms of the GNU General Public License, v2 or later 
 * Author: Brad House <brad@mainstreetsoftworks.com>
 *    
 * $Header: /var/cvsroot/gentoo-src/portage/src/sandbox-1.1/Attic/sandbox.h,v 1.5.2.1 2004/10/22 16:53:30 carpaski Exp $
 */

#ifndef __SANDBOX_H__
#define __SANDBOX_H__

/* Uncomment below to use flock instead of fcntl (POSIX way) to lock/unlock files */
/* #define USE_FLOCK */

/* Uncomment below to use system() to execute the shell rather than execv */
/* #define USE_SYSTEM_SHELL */

/* Uncomment below to use /etc/ld.so.preload (could be very intrusive!!) */
/* #define USE_LD_SO_PRELOAD */

/* Uncommend to not have the protected shell forked, just run in parent process */
/* ONLY FOR DEBUGGING PURPOSES!! (strace needs it like that) */
/* #define NO_FORK */

#define LD_PRELOAD_FILE		"/etc/ld.so.preload"
#define LIB_NAME		"libsandbox.so"
#define BASHRC_NAME		"sandbox.bashrc"
#define PIDS_FILE		"/tmp/sandboxpids.tmp"
#define LOG_FILE_PREFIX		"/tmp/sandbox-"
#define DEBUG_LOG_FILE_PREFIX	"/tmp/sandbox-debug-"
#define LOG_FILE_EXT		".log"

#define ENV_SANDBOX_DEBUG_LOG	"SANDBOX_DEBUG_LOG"
#define ENV_SANDBOX_LOG		"SANDBOX_LOG"
#define ENV_SANDBOX_DIR		"SANDBOX_DIR"
#define ENV_SANDBOX_LIB		"SANDBOX_LIB"

#define ENV_SANDBOX_DENY	"SANDBOX_DENY"
#define ENV_SANDBOX_READ	"SANDBOX_READ"
#define ENV_SANDBOX_WRITE	"SANDBOX_WRITE"
#define ENV_SANDBOX_PREDICT	"SANDBOX_PREDICT"

#define ENV_SANDBOX_ON		"SANDBOX_ON"
#define ENV_SANDBOX_BEEP	"SANDBOX_BEEP"

#define DEFAULT_BEEP_COUNT	3

char *get_sandbox_path(char *argv0);
char *get_sandbox_lib(char *sb_path);
char *get_sandbox_pids_file(void);
char *get_sandbox_rc(char *sb_path);
char *get_sandbox_log();
char *sb_dirname(const char *path);
int file_getmode(char *mode);
long file_tell(int fp);
int file_lock(int fd, int lock, char *filename);
int file_unlock(int fd);
int file_locktype(char *mode);
int file_open(char *filename, char *mode, int perm_specified, ...);
void file_close(int fd);
long file_length(int fd);
int file_truncate(int fd);
int file_exist(char *filename, int checkmode);

#endif

// vim:expandtab noai:cindent ai
