/*	
**	Path sandbox for the gentoo linux portage package system, initially
**	based on the ROCK Linux Wrapper for getting a list of created files
**
**  to integrate with bash, bash should have been built like this
**
**  ./configure --prefix=<prefix> --host=<host> --without-gnu-malloc
**
**  it's very important that the --enable-static-link option is NOT specified
**	
**	Copyright (C) 2001 Geert Bevin, Uwyn, http://www.uwyn.com
**	Distributed under the terms of the GNU General Public License, v2 or later 
**	Author : Geert Bevin <gbevin@uwyn.com>
**  $Id: /var/cvsroot/gentoo-src/portage/src/sandbox/Attic/libsandbox.c,v 1.8 2002/08/05 05:51:39 drobbins Exp $
*/

#define _GNU_SOURCE
#define _REENTRANT

#define open xxx_open
#define open64 xxx_open64
#  include <dirent.h>
#  include <dlfcn.h>
#  include <errno.h>
#  include <fcntl.h>
#  include <stdarg.h>
#  include <stdio.h>
#  include <stdlib.h>
#  include <string.h>
#  include <sys/file.h>
#  include <sys/stat.h>
#  include <sys/types.h>
#  include <unistd.h>
#  include <utime.h>
#undef open
#undef open64

#define PIDS_FILE	"/tmp/sandboxpids.tmp"

typedef struct {
	int		show_access_violation;
	char**	deny_prefixes;
	int		num_deny_prefixes;
	char**	read_prefixes;
	int		num_read_prefixes;
	char**	write_prefixes;
	int		num_write_prefixes;
	char**	predict_prefixes;
	int		num_predict_prefixes;
	char**	write_denied_prefixes;
	int		num_write_denied_prefixes;
} sbcontext_t;

int 	check_access(sbcontext_t*, const char*, const char*);
int 	check_syscall(sbcontext_t*, const char*, const char*);
int 	before_syscall(const char*, const char*);
int 	before_syscall_open_int(const char*, const char*, int);
int 	before_syscall_open_char(const char*, const char*, const char*);
void 	clean_env_entries(char***, int*);
char*	filter_path(const char*);
void*	get_dl_symbol(char*);
void	init_context(sbcontext_t*);
void 	init_env_entries(char***, int*, char*, int);
int		is_sandbox_on();
int		is_sandbox_pid();

/* Wrapper macros and functions */

/* macro definition to wrap functions before and after the
   execution of basic file related system-calls.
  
   nr   : the argument number of the system-call's argument that
          contains the file name to monitor
   rt   : the return type of the system call
   name : the name of the function call
   arg1, arg2, arg3 : the types of the function call's arguments
   fl   : the argument number of the system-call's argument that
          contains the file access flags
   md   : the argument number of the system-call's argument that
          contains the file access mode
*/
#define wrsysc3(nr, rt, name, arg1, arg2, arg3)								\
																			\
/* the function call is defined externally from this file */				\
extern rt name(arg1, arg2, arg3);											\
																			\
/* orig_ ## name is a pointer to a function with three arguments and the 
   return type of the system call. This will be used to store the pointer
   to the system call function and call it. */								\
rt (*orig_ ## name)(arg1, arg2, arg3) = NULL;								\
																			\
rt name(arg1 a1, arg2 a2, arg3 a3)											\
{																			\
	rt result = -1;															\
	int old_errno = errno;													\
	if (0 == is_sandbox_on() || 1 == before_syscall(#name, a ## nr))		\
	{																		\
		if (!orig_ ## name)													\
		{																	\
			orig_ ## name = get_dl_symbol(#name);							\
		}																	\
		errno = old_errno;													\
		result = orig_ ## name(a1, a2, a3);									\
	}																		\
	return result;															\
}

#define wrsysc2(nr, rt, name, arg1, arg2)									\
extern rt name(arg1, arg2);													\
rt (*orig_ ## name)(arg1, arg2) = NULL;										\
																			\
rt name(arg1 a1, arg2 a2)													\
{																			\
	rt result = -1;															\
	int old_errno = errno;													\
	if (0 == is_sandbox_on() || 1 == before_syscall(#name, a ## nr))		\
	{																		\
		if (!orig_ ## name)													\
		{																	\
			orig_ ## name = get_dl_symbol(#name);							\
		}																	\
		errno = old_errno;													\
		result = orig_ ## name(a1, a2);										\
	}																		\
	return result;															\
}

#define wrsysc1(nr, rt, name, arg1)											\
extern rt name(arg1);														\
rt (*orig_ ## name)(arg1) = NULL;											\
																			\
rt name(arg1 a1)															\
{																			\
	rt result = -1;															\
	int old_errno = errno;													\
	if (0 == is_sandbox_on() || 1 == before_syscall(#name, a ## nr))		\
	{																		\
		if (!orig_ ## name)													\
		{																	\
			orig_ ## name = get_dl_symbol(#name);							\
		}																	\
		errno = old_errno;													\
		result = orig_ ## name(a1);											\
	}																		\
	return result;															\
}

#define wrsysc1ptr(nr, rt, name, arg1)										\
extern rt name(arg1);														\
rt (*orig_ ## name)(arg1) = NULL;											\
																			\
rt name(arg1 a1)															\
{																			\
	rt result = NULL;														\
	int old_errno = errno;													\
	if (0 == is_sandbox_on() || 1 == before_syscall(#name, a ## nr))		\
	{																		\
		if (!orig_ ## name)													\
		{																	\
			orig_ ## name = get_dl_symbol(#name);							\
		}																	\
		errno = old_errno;													\
		result = orig_ ## name(a1);											\
	}																		\
	return result;															\
}

#define wropenint3(nr, fl, rt, name, arg1, arg2, arg3)						\
extern rt name(arg1, arg2, arg3);											\
rt (*orig_ ## name)(arg1, arg2, arg3) = NULL;								\
																			\
rt name(arg1 a1, arg2 a2, arg3 a3)											\
{																			\
	rt result = -1; 														\
	int old_errno = errno;													\
	if (0 == is_sandbox_on() || 											\
		1 == before_syscall_open_int(#name, a ## nr, a ## fl))				\
	{																		\
		if (!orig_ ## name)													\
		{																	\
			orig_ ## name = get_dl_symbol(#name);							\
		}																	\
		errno = old_errno;													\
		result = orig_ ## name(a1, a2, a3);									\
	}																		\
	return result;															\
}

#define wropenchar2(nr, md, rt, name, arg1, arg2)							\
extern rt name(arg1, arg2);													\
rt (*orig_ ## name)(arg1, arg2) = NULL;										\
																			\
rt name(arg1 a1, arg2 a2)													\
{																			\
	rt result = NULL;														\
	int old_errno = errno;													\
	if (0 == is_sandbox_on() || 											\
		1 == before_syscall_open_char(#name, a ## nr, a ## md))				\
	{																		\
		if (!orig_ ## name)													\
		{																	\
			orig_ ## name = get_dl_symbol(#name);							\
		}																	\
		errno = old_errno;													\
		result = orig_ ## name(a1, a2);										\
	}																		\
	return result;															\
}

#define wropenchar3(nr, md, rt, name, arg1, arg2, arg3)						\
extern rt name(arg1, arg2, arg3);											\
rt (*orig_ ## name)(arg1, arg2, arg3) = NULL;								\
																			\
rt name(arg1 a1, arg2 a2, arg3 a3)											\
{																			\
	rt result = NULL;														\
	int old_errno = errno;													\
	if (0 == is_sandbox_on() || 											\
		1 == before_syscall_open_char(#name, a ## nr, a ## md))				\
	{																		\
		if (!orig_ ## name)													\
		{																	\
			orig_ ## name = get_dl_symbol(#name);							\
		}																	\
		errno = old_errno;													\
		result = orig_ ## name(a1, a2, a3);									\
	}																		\
	return result;															\
}

#define wrexec3(nr, rt, name, arg1, arg2, arg3)								\
extern rt name(arg1, arg2, arg3);											\
rt (*orig_ ## name)(arg1, arg2, arg3) = NULL;								\
																			\
rt name(arg1 a1, arg2 a2, arg3 a3)											\
{																			\
	rt result = -1;															\
	int old_errno = errno;													\
	if (0 == is_sandbox_on() || 1 == before_syscall(#name, a ## nr))		\
	{																		\
		if (!orig_ ## name)													\
		{																	\
			orig_ ## name = get_dl_symbol(#name);							\
		}																	\
		errno = old_errno;													\
		result = orig_ ## name(a1, a2, a3);									\
	}																		\
	return result;															\
}

#define wrexec2(nr, rt, name, arg1, arg2)									\
extern rt name(arg1, arg2);													\
rt (*orig_ ## name)(arg1, arg2) = NULL;										\
																			\
rt name(arg1 a1, arg2 a2)													\
{																			\
	rt result = -1;															\
	int old_errno = errno;													\
	if (0 == is_sandbox_on() || 1 == before_syscall(#name, a ## nr))		\
	{																		\
		if (!orig_ ## name)													\
		{																	\
			orig_ ## name = get_dl_symbol(#name);							\
		}																	\
		errno = old_errno;													\
		result = orig_ ## name(a1, a2);										\
	}																		\
	return result;															\
}

#define wrexec2va(nr, rt, name, arg1, arg2)									\
extern rt name(arg1, arg2, ...);											\
rt (*orig_ ## name)(arg1, arg2, ...) = NULL;								\
																			\
rt name(arg1 a1, arg2 a2, ...)												\
{																			\
	void* result = NULL; 													\
	int old_errno = errno;													\
	if (0 == is_sandbox_on() || 1 == before_syscall(#name, a ## nr))		\
	{																		\
		if (!orig_ ## name)													\
		{																	\
			orig_ ## name = get_dl_symbol(#name);							\
		}																	\
		errno = old_errno;													\
		result = __builtin_apply( (void(*)()) orig_ ## name, 				\
									__builtin_apply_args(), 32 );			\
		old_errno = errno;													\
	}																		\
	if (NULL == result)														\
	{																		\
		return -1;															\
	}																		\
	else																	\
	{																		\
		__builtin_return(result);											\
	}																		\
}

wropenint3(1, 2, int, open,   const char*, int, mode_t)
wropenint3(1, 2, int, open64, const char*, int, mode_t)

wropenchar2(1, 2, FILE*, fopen,   const char*, const char*)
wropenchar2(1, 2, FILE*, fopen64, const char*, const char*)
wropenchar3(1, 2, FILE*, freopen, const char*, const char*, FILE*)

wropenchar2(1, 2, FILE*, popen,   const char*, const char*)

// write syscalls

wrsysc2(1, int, creat,   const char*, mode_t)
wrsysc2(1, int, creat64, const char*, mode_t)

wrsysc2(1, int, mkdir,  const char*, mode_t)
wrsysc3(1, int, mknod,  const char*, mode_t, dev_t)
wrsysc2(1, int, mkfifo, const char*, mode_t)

wrsysc2(2, int, link,    const char*, const char*)
wrsysc2(2, int, symlink, const char*, const char*)
wrsysc2(2, int, rename,  const char*, const char*)

wrsysc2(1, int, utime,  const char*, const struct utimbuf*)
wrsysc2(1, int, utimes, const char*, struct timeval*)

wrsysc1(1, int, unlink, const char*)
wrsysc1(1, int, rmdir,  const char*)

wrsysc3(1, int, chown,  const char*, uid_t, gid_t)
wrsysc3(1, int, lchown, const char*, uid_t, gid_t)

wrsysc2(1, int, chmod, const char*, mode_t)

/* read syscalls */

wrsysc1ptr(1, DIR*, opendir, const char*)

/* execution syscalls */
wrsysc1(1, int, system, const char*)

wrexec2va(1, int, execl,  const char*, const char*)
wrexec2va(1, int, execle, const char*, const char*)
wrexec2(1, int, execv,    const char*, char* const*)
wrexec3(1, int, execve,   const char*, char* const*, char* const*)
/* execlp is redirected to execvp */
/* execvp is special since it should search the PATH var entries */
extern int execvp(const char*, char* const*);
int(*orig_execvp)(const char*, char* const*) = NULL;
int execvp(const char* file, char* const* argv)
{
	int		result = -1;
	int		old_errno = errno;
	int		i = 0;
	int		allowed = 1;
	char**	path_entries = NULL;
	int		num_path_entries = 0;
	char	constructed_path[255];

	if (1 == is_sandbox_on())
	{
		init_env_entries(&path_entries, &num_path_entries, "PATH", 0);
		for (i = 0; i < num_path_entries; i++)
		{
			strcpy(constructed_path, path_entries[i]);
			strcat(constructed_path, "/");
			strcat(constructed_path, file);
			if (0 == before_syscall("execvp", constructed_path))
			{
				allowed = 0;
				break;
			}
		}
		clean_env_entries(&path_entries, &num_path_entries);
	}
	
	if (1 == allowed)
	{
		if (!orig_execvp)
		{
			orig_execvp = get_dl_symbol("execvp");
		}
		errno = old_errno;
		result = orig_execvp(file, argv);
		old_errno = errno;
	}
	errno = old_errno;
	return result;
}

/* lseek, lseek64, fdopen, fchown, fchmod, fcntl, lockf
   are not wrapped since they can't be used if open is wrapped correctly
   and unaccessible file descriptors are not possible to create */

void* get_dl_symbol(char* symname)
{
	void* result = dlsym(RTLD_NEXT, symname);
	if (0 == result)
	{
		fprintf(stderr, "Sandbox : can't resolve %s: %s.\n", symname, dlerror());
		abort();
	}
	return result;
}

void init_context(sbcontext_t* context)
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

int is_sandbox_pid()
{
	int		result = 0;
	FILE*	pids_stream = NULL;
	int		pids_file = -1;
	int		current_pid = 0;
	int		tmp_pid = 0;
	
	pids_stream = fopen(PIDS_FILE, "r");
	if (NULL == pids_stream)
	{
		perror(">>> pids file fopen");
	}
	else
	{
		pids_file = fileno(pids_stream);
		if (pids_file < 0)
		{
			perror(">>> pids file fileno");
		}
		else
		{
			current_pid = getpid();

			while (EOF != fscanf(pids_stream, "%d\n", &tmp_pid))
			{
				if (tmp_pid == current_pid)
				{
					result = 1;
					break;
				}
			}
		}
		if (EOF == fclose(pids_stream))
		{
			perror(">>> pids file fclose");
		}
		pids_stream = NULL;
		pids_file = -1;
	}

	return result;
}

void clean_env_entries(char*** prefixes_array, int* prefixes_num)
{
	int i = 0;
	if (NULL != *prefixes_array)
	{
		for (i = 0; i < *prefixes_num; i++)
		{
			if (NULL != (*prefixes_array)[i])
			{
				free((*prefixes_array)[i]);
				(*prefixes_array)[i] = NULL;
			}
		}
		free(*prefixes_array);
		*prefixes_array = NULL;

		*prefixes_num = 0;
	}
}

void init_env_entries(char*** prefixes_array, int* prefixes_num, char* env, int warn)
{
	char* prefixes_env = getenv(env);

	if (NULL == prefixes_env)
	{
		fprintf(stderr, "Sandbox error : the %s environmental variable should be defined.\n", env);
	}
	else
	{
		char*	buffer = NULL;
		int		prefixes_env_length = strlen(prefixes_env);
		int		i = 0;
		int		num_delimiters = 0;
		char*	token = NULL;
		char*	prefix = NULL;

		for (i = 0; i < prefixes_env_length; i++)
		{
			if (':' == prefixes_env[i])
			{
				num_delimiters++;
			}
		}

		if (num_delimiters > 0)
		{
			buffer = (char*)malloc(sizeof(char)*(prefixes_env_length+1));
			*prefixes_array = (char**)malloc(sizeof(char*)*(num_delimiters+1));

			strcpy(buffer, prefixes_env);
			token = strtok(buffer, ":");
			while (NULL != token &&
				   strlen(token) > 0)
			{
				prefix = (char*)malloc(sizeof(char)*(strlen(token)+1));
				strcpy(prefix, token);
				(*prefixes_array)[(*prefixes_num)++] = filter_path(prefix);
				free(prefix);
				token = strtok(NULL, ":");
			}
			free(buffer);
			buffer = NULL;
		}
		else if(prefixes_env_length > 0)
		{
			(*prefixes_array) = (char**)malloc(sizeof(char*));
			
			prefix = (char*)malloc(sizeof(char)*(prefixes_env_length+1));
			strcpy(prefix, prefixes_env);
			(*prefixes_array)[(*prefixes_num)++] = filter_path(prefix);
			free(prefix);
		}
	}
}

char* filter_path(const char* path)
{
	int		initial_path_length = strlen(path);
	char*	filtered_path = (char*)malloc(sizeof(char)*(initial_path_length+1));
	int		i = 0;
	int		j = 0;
	
	for (i = 0, j = 0; i < initial_path_length;)
	{
		filtered_path[j] = path[i];
		if ('/' == filtered_path[j])
		{
			while ('/' == path[i] &&
				   i < initial_path_length)
			{
				i++;
			}
		}
		else
		{
			i++;
		}
		j++;
	}
	filtered_path[j] = 0;

	return filtered_path;
}

int check_access(sbcontext_t* sbcontext, const char* func, const char* path)
{
	int		result = -1;
	int		i = 0;
	char*	filtered_path = filter_path(path);

	if ('/' != path[0])
	{
		return 0;
	}

	if (0 == strcmp(filtered_path, "/etc/ld.so.preload") &&
		is_sandbox_pid())
	{
		result = 1;
	}
	
	if (-1 == result)
	{
		if (NULL != sbcontext->deny_prefixes)
		{
			for (i = 0; i < sbcontext->num_deny_prefixes; i++)
			{
				if (0 == strncmp(filtered_path, sbcontext->deny_prefixes[i], strlen(sbcontext->deny_prefixes[i])))
				{
					result = 0;
					break;
				}
			}
		}

		if (-1 == result)
		{
			if (NULL != sbcontext->read_prefixes &&
				(0 == strcmp(func, "open_rd") ||
				 0 == strcmp(func, "popen") ||
				 0 == strcmp(func, "opendir") ||
				 0 == strcmp(func, "system") ||
				 0 == strcmp(func, "execl") ||
				 0 == strcmp(func, "execlp") ||
				 0 == strcmp(func, "execle") ||
				 0 == strcmp(func, "execv") ||
				 0 == strcmp(func, "execvp") ||
				 0 == strcmp(func, "execve")))
			{
				for (i = 0; i < sbcontext->num_read_prefixes; i++)
				{
					if (0 == strncmp(filtered_path, sbcontext->read_prefixes[i], strlen(sbcontext->read_prefixes[i])))
					{
						result = 1;
						break;
					}
				}
			}
			else if (NULL != sbcontext->write_prefixes &&
					 (0 == strcmp(func, "open_wr") ||
					  0 == strcmp(func, "creat") ||
					  0 == strcmp(func, "creat64") ||
					  0 == strcmp(func, "mkdir") ||
					  0 == strcmp(func, "mknod") ||
					  0 == strcmp(func, "mkfifo") ||
					  0 == strcmp(func, "link") ||
					  0 == strcmp(func, "symlink") ||
					  0 == strcmp(func, "rename") ||
					  0 == strcmp(func, "utime") ||
					  0 == strcmp(func, "utimes") ||
					  0 == strcmp(func, "unlink") ||
					  0 == strcmp(func, "rmdir") ||
					  0 == strcmp(func, "chown") ||
					  0 == strcmp(func, "lchown") ||
					  0 == strcmp(func, "chmod")))
			{
				struct stat	tmp_stat;

				for (i = 0; i < sbcontext->num_write_denied_prefixes; i++)
				{
					if (0 == strncmp(filtered_path, sbcontext->write_denied_prefixes[i], strlen(sbcontext->write_denied_prefixes[i])))
					{
						result = 0;
						break;
					}
				}
				if (-1 == result)
				{
					for (i = 0; i < sbcontext->num_write_prefixes; i++)
					{
						if (0 == strncmp(filtered_path, sbcontext->write_prefixes[i], strlen(sbcontext->write_prefixes[i])))
						{
							result = 1;
							break;
						}
					}

					if (-1 == result)
					{
						/* hack to prevent mkdir of existing dirs to show errors */
						if (strcmp(func, "mkdir") == 0)
						{
							if (0 == stat(filtered_path, &tmp_stat))
							{
								sbcontext->show_access_violation = 0;
								result = 0;
							}
						}

						if (-1 == result)
						{
							for (i = 0; i < sbcontext->num_predict_prefixes; i++)
							{
								if (0 == strncmp(filtered_path, sbcontext->predict_prefixes[i], strlen(sbcontext->predict_prefixes[i])))
								{
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
	
	if (-1 == result)
	{
		result = 0;
	}

	free(filtered_path);

	return result;
}

int check_syscall(sbcontext_t* sbcontext, const char* func, const char* file)
{
	int			result = 1;
	char*		absolute_path = NULL;
	char*		tmp_buffer = NULL;
	struct stat	log_stat;
	char*		log_path = NULL;
	int 		log_file = 0;
	struct stat	debug_log_stat;
	char*		debug_log_env = NULL;
	char*		debug_log_path = NULL;
	int 		debug_log_file = 0;
	char 		buffer[512];

	if ('/' == file[0])
	{
		absolute_path = (char*)malloc(sizeof(char)*(strlen(file)+1));
		sprintf(absolute_path, "%s", file);
	}
	else
	{
		tmp_buffer = get_current_dir_name();
		absolute_path = (char*)malloc(sizeof(char)*(strlen(tmp_buffer)+1+strlen(file)+1));
		sprintf(absolute_path,"%s/%s", tmp_buffer, file);
		free(tmp_buffer);
		tmp_buffer = NULL;
	}
	
	log_path = getenv("SANDBOX_LOG");
	debug_log_env = getenv("SANDBOX_DEBUG");
	debug_log_path = getenv("SANDBOX_DEBUG_LOG");
	
	if ((NULL == log_path || 0 != strcmp(absolute_path, log_path)) &&
		(NULL == debug_log_env || NULL == debug_log_path || 0 != strcmp(absolute_path, debug_log_path)) &&
		0 == check_access(sbcontext, func, absolute_path))
	{
		if (1 == sbcontext->show_access_violation)
		{
			fprintf(stderr, "\e[31;01mACCESS DENIED\033[0m  %s:%*s%s\n", func, (int)(10-strlen(func)), "", absolute_path);
			
			if (NULL != log_path)
			{
				sprintf(buffer, "%s:%*s%s\n", func, (int)(10-strlen(func)), "", absolute_path);
				if (0 == lstat(log_path, &log_stat) &&
					0 == S_ISREG(log_stat.st_mode))
				{
					fprintf(stderr, "\e[31;01mSECURITY BREACH\033[0m  %s already exists and is not a regular file.\n", log_path);
				}
				else
				{
					log_file = open(log_path, O_APPEND|O_WRONLY|O_CREAT, S_IRUSR|S_IWUSR|S_IRGRP|S_IROTH);
					if(log_file >= 0)
					{
						write(log_file, buffer, strlen(buffer));
						close(log_file);
					}
				}
			}
		}

		result = 0;
	}
	else if (NULL != debug_log_env)
	{
		if (NULL != debug_log_path)
		{
			if (0 != strcmp(absolute_path, debug_log_path))
			{
				sprintf(buffer, "%s:%*s%s\n", func, (int)(10-strlen(func)), "", absolute_path);
				if (0 == lstat(debug_log_path, &debug_log_stat) &&
					0 == S_ISREG(debug_log_stat.st_mode))
				{
					fprintf(stderr, "\e[31;01mSECURITY BREACH\033[0m  %s already exists and is not a regular file.\n", log_path);
				}
				else
				{
					debug_log_file = open(debug_log_path, O_APPEND|O_WRONLY|O_CREAT, S_IRUSR|S_IWUSR|S_IRGRP|S_IROTH);
					if(debug_log_file >= 0)
					{
						write(debug_log_file, buffer, strlen(buffer));
						close(debug_log_file);
					}
				}
			}
		}
		else
		{
			fprintf(stderr, "\e[32;01mACCESS ALLOWED\033[0m %s:%*s%s\n", func, (int)(10-strlen(func)), "", absolute_path);
		}
	}

	free(absolute_path);
	absolute_path = NULL;
	
	return result;
}

int is_sandbox_on()
{
	/* $SANDBOX_ACTIVE is an env variable that should ONLY
	 * be used internal by sandbox.c and libsanbox.c.  External
	 * sources should NEVER set it, else the sandbox is enabled
	 * in some cases when run in parallel with another sandbox,
	 * but not even in the sandbox shell.
	 *
	 * Azarah (3 Aug 2002)
	 */
	if (NULL != getenv("SANDBOX_ON") &&
		0 == strcmp(getenv("SANDBOX_ON"), "1") &&
		NULL != getenv("SANDBOX_ACTIVE") &&
		0 == strcmp(getenv("SANDBOX_ACTIVE"), "armedandready"))
	{
		return 1;
	}
	else
	{
		return 0;
	}
}

int before_syscall(const char* func, const char* file)
{
	int 		result = 1;

	sbcontext_t	sbcontext;

	init_context(&sbcontext);

	init_env_entries(&(sbcontext.deny_prefixes), &(sbcontext.num_deny_prefixes), "SANDBOX_DENY", 1);
	init_env_entries(&(sbcontext.read_prefixes), &(sbcontext.num_read_prefixes), "SANDBOX_READ", 1);
	init_env_entries(&(sbcontext.write_prefixes), &(sbcontext.num_write_prefixes), "SANDBOX_WRITE", 1);
	init_env_entries(&(sbcontext.predict_prefixes), &(sbcontext.num_predict_prefixes), "SANDBOX_PREDICT", 1);

	result = check_syscall(&sbcontext, func, file);

	clean_env_entries(&(sbcontext.deny_prefixes), &(sbcontext.num_deny_prefixes));
	clean_env_entries(&(sbcontext.read_prefixes), &(sbcontext.num_read_prefixes));
	clean_env_entries(&(sbcontext.write_prefixes), &(sbcontext.num_write_prefixes));
	clean_env_entries(&(sbcontext.predict_prefixes), &(sbcontext.num_predict_prefixes));
	
	if (0 == result)
	{
		errno = EACCES;
	}

	return result;
}

int before_syscall_open_int(const char* func, const char* file, int flags)
{
	if (flags & O_WRONLY ||
		flags & O_RDWR)
	{
		return before_syscall("open_wr", file);
	}
	else
	{
		return before_syscall("open_rd", file);
	}
}

int before_syscall_open_char(const char* func, const char* file, const char* mode)
{
	if (strcmp(mode, "r") == 0 ||
		strcmp(mode, "rb") == 0)
	{
		return before_syscall("open_rd", file);
	}
	else
	{
		return before_syscall("open_wr", file);
	}
}
