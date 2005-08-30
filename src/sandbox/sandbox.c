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
**  $Id: /var/cvsroot/gentoo-src/portage/src/sandbox/Attic/sandbox.c,v 1.13 2002/08/05 05:51:39 drobbins Exp $
*/

#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <limits.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>   
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#define LD_PRELOAD_FILE			"/etc/ld.so.preload"
#define LIB_NAME				"libsandbox.so"
#define BASHRC_NAME				"sandbox.bashrc"
#define PIDS_FILE				"/tmp/sandboxpids.tmp"
#define LOG_FILE_PREFIX			"/tmp/sandbox-"
#define DEBUG_LOG_FILE_PREFIX	"/tmp/sandbox-debug-"
#define LOG_FILE_EXT			".log"

#define ENV_SANDBOX_DEBUG_LOG	"SANDBOX_DEBUG_LOG"
#define ENV_SANDBOX_LOG			"SANDBOX_LOG"
#define ENV_SANDBOX_DIR			"SANDBOX_DIR"
#define ENV_SANDBOX_LIB			"SANDBOX_LIB"

#define ENV_SANDBOX_DENY		"SANDBOX_DENY"
#define ENV_SANDBOX_READ		"SANDBOX_READ"
#define ENV_SANDBOX_WRITE		"SANDBOX_WRITE"
#define ENV_SANDBOX_PREDICT		"SANDBOX_PREDICT"

#define ENV_SANDBOX_ON			"SANDBOX_ON"
#define ENV_SANDBOX_BEEP		"SANDBOX_BEEP"

#define DEFAULT_BEEP_COUNT	3

int	preload_adaptable = 1;
int cleaned_up = 0;

char* dirname(const char* path)
{
  char*			base = NULL;
  unsigned int	length = 0;
  
  base = strrchr(path, '/');
  if (NULL == base)
  {
	  return strdup(".");
  }
  while (base > path &&
		 *base == '/')
  {
	  base--;
  }
  length = (unsigned int) 1 + base - path;
  
  base = malloc(sizeof(char)*(length+1));
  memmove(base, path, length);
  base[length] = 0;
  
  return base;
}

void cleanup()
{
	int			i = 0;
	int			success = 1;

	FILE*		preload_stream = NULL;
	int			preload_file = -1;
	char		preload_entry[255];
	char**		preload_array = NULL;
	int			num_of_preloads = 0;
	
	FILE*		pids_stream = NULL;
	struct stat	pids_stat;
	int			pids_file = -1;
	char		pid_string[255];
	int			tmp_pid = 0;
	int*		pids_array = NULL;
	int			num_of_pids = 0;

	/* remove this sandbox's bash pid from the global pids file if it has rights to adapt the ld.so.preload file*/
	if (1 == preload_adaptable &&
		0 == cleaned_up)
	{
		cleaned_up = 1;
		success = 1;
		if (0 == lstat(PIDS_FILE, &pids_stat) &&
			0 == S_ISREG(pids_stat.st_mode))
		{
			perror(">>> pids file is not a regular file");
			success = 0;
		}
		else
		{
			pids_stream = fopen(PIDS_FILE, "r+");
			if (NULL == pids_stream)
			{
				perror(">>> pids file fopen");
				success = 0;
			}
			else
			{
				pids_file = fileno(pids_stream);
				if (pids_file < 0)
				{
					perror(">>> pids file fileno");
					success = 0;
				}
				else
				{
					if (flock(pids_file, LOCK_EX) < 0)
					{
						perror(">>> pids file lock");
						success = 0;
					}
					else
					{
						/* check which sandbox pids are still running */
						while (EOF != fscanf(pids_stream, "%d\n", &tmp_pid))
						{
							if (0 == kill(tmp_pid, 0))
							{
								if (NULL == pids_array)
								{
									pids_array = (int*)malloc(sizeof(int));
								}
								else
								{
									pids_array = (int*)realloc(pids_array, sizeof(int)*(num_of_pids+1));
								}
								pids_array[num_of_pids++] = tmp_pid;
							}
						}
	
						/* clean the /etc/ld.so.preload file if no other sandbox processes are running anymore*/
						if(num_of_pids == 1)
						{
							success = 1;
							preload_stream = fopen("/etc/ld.so.preload", "r+");
							if (NULL == preload_stream)
							{
								perror(">>> /etc/ld.so.preload file fopen");
								success = 0;
							}
							else
							{
								preload_file = fileno(preload_stream);
								if (preload_file < 0)
								{
									perror(">>> /etc/ld.so.preload file fileno");
									success = 0;
								}
								else
								{
									if (flock(preload_file, LOCK_EX) < 0)
									{
										perror(">>> /etc/ld.so.preload file lock");
										success = 0;
									}
									else
									{
										/* only get the entries that don't contain the sandbox library from the /etc/ld.so.preload file */
										while (EOF != fscanf(preload_stream, "%s\n", preload_entry))
										{
											if (NULL == strstr(preload_entry, LIB_NAME))
											{
												if (NULL == preload_array)
												{
													preload_array = (char**)malloc(sizeof(char*));
												}
												else
												{
													preload_array = (char**)realloc(pids_array, sizeof(char*)*(num_of_preloads+1));
												}
												preload_array[num_of_preloads++] = strdup(preload_entry);
											}
										}
	
										if (fseek(preload_stream, 0, SEEK_SET) < 0)
										{
											perror(">>> /etc/ld.so.preload file fseek");
											success = 0;
										}
										else
										{
											/* empty the /etc/ld.so.preload file */
											if (ftruncate(preload_file, 0) < 0)
											{
												perror(">>> /etc/ld.so.preload file ftruncate");
												success = 0;
											}
											else
											{
												/* store the other preload libraries back into the /etc/ld.so.preload file */
												if(num_of_preloads > 0)
												{
													for (i = 0; i < num_of_preloads; i++)
													{
														sprintf(preload_entry, "%s\n", preload_array[i]);
														if (write(preload_file, preload_entry, strlen(preload_entry)) != strlen(preload_entry))
														{
															perror(">>> /etc/ld.so.preload file write");
															success = 0;
															break;
														}
													}
												}
											}
										}
	
										if (NULL != preload_array)
										{
											for (i = 0; i < num_of_preloads; i++)
											{
												free(preload_array[i]);
												preload_array[i] = NULL;
											}
											free(preload_array);
											preload_array = NULL;
										}
	
										if (flock(preload_file, LOCK_UN) < 0)
										{
											perror(">>> /etc/ld.so.preload file unlock");
											success = 0;
										}
									}
								}
								if (EOF == fclose(preload_stream))
								{
									perror(">>> /etc/ld.so.preload file fclose");
									success = 0;
								}
								preload_stream = NULL;
								preload_file = -1;
							}
						}
	
						if (fseek(pids_stream, 0, SEEK_SET) < 0)
						{
							perror(">>> pids file fseek");
							success = 0;
						}
						else
						{
							/* empty the pids file */
							if (ftruncate(pids_file, 0) < 0)
							{
								perror(">>> pids file ftruncate");
								success = 0;
							}
							else
							{
								/* if pids are still running, write only the running pids back to the file */
								if(num_of_pids > 1)
								{
									for (i = 0; i < num_of_pids; i++)
									{
										sprintf(pid_string, "%d\n", pids_array[i]);
										if (write(pids_file, pid_string, strlen(pid_string)) != strlen(pid_string))
										{
											perror(">>> pids file write");
											success = 0;
											break;
										}
									}
								}
							}
						}
	
						if (NULL != pids_array)
						{
							free(pids_array);
							pids_array = NULL;
						}
	
						if (flock(pids_file, LOCK_UN) < 0)
						{
							perror(">>> pids file unlock");
							success = 0;
						}
					}
				}
				if (EOF == fclose(pids_stream))
				{
					perror(">>> pids file fclose");
					success = 0;
				}
				pids_stream = NULL;
				pids_file = -1;
			}
		}
		if (0 == success)
		{
			exit(1);
		}
	}
}

void stop(int signum)
{
	cleanup();
}

int main(int argc, char** argv)
{
	int			i = 0;
	int			success = 1;
	int			status = 0;
	char*		run_str = "-c";
	char		run_arg[255];
		
	struct stat	preload_stat;
	FILE*		preload_stream = NULL;
	int			preload_file = -1;
	char		preload_entry[255];
	int			preload_lib_present = 0;

	int			bash_pid = 0;
	char*		home_dir = NULL;
	char		portage_tmp_dir[PATH_MAX];
	char		var_tmp_dir[PATH_MAX];
	char		tmp_dir[PATH_MAX];
	char		sandbox_write_var[255];
	char		sandbox_predict_var[255];
	char*		tmp_string = NULL;
	char		full_sandbox_path[255];
	char		sandbox_log[255];
	char*		sandbox_log_env;
	struct stat	sandbox_log_stat;
	int			sandbox_log_presence = 0;
	int			sandbox_log_file = -1;
	char		sandbox_debug_log[255];
	char		sandbox_dir[255];
	char		sandbox_lib[255];
	struct stat	sandbox_lib_stat;
	char		sandbox_rc[255];
	struct stat	sandbox_rc_stat;

	struct stat	pids_stat;
	int			pids_file = -1;
	char		pid_string[255];

	// Only print info if called with no arguments ....
	if (argc < 2)
	{
		printf("========================== Gentoo linux path sandbox ===========================\n");
	}

	/* check if a sandbox is already running */
	if (NULL != getenv(ENV_SANDBOX_ON))
	{
		fprintf(stderr, "Not launching a new sandbox instance\nAnother one is already running in this process hierarchy.\n");

		exit(1);
	}
	else
	{
		char* argv_bash[] = 
		{
			"/bin/bash",
			"-rcfile",
			NULL,
			NULL,
			NULL,
			NULL
		};

		/* determine the location of all the sandbox support files */
		if (argc < 2)
			printf("Detection of the support files.\n");
		if ('/' == argv[0][0])
		{
			strcpy(full_sandbox_path, argv[0]);
		}
		else
		{
			tmp_string = get_current_dir_name();
			strcpy(full_sandbox_path, tmp_string);
			free(tmp_string);
			tmp_string = NULL;
			strcat(full_sandbox_path, "/");
			strcat(full_sandbox_path, argv[0]);
		}
		tmp_string = dirname(full_sandbox_path);
		strcpy(sandbox_dir, tmp_string);
		free(tmp_string);
		tmp_string = NULL;
		strcat(sandbox_dir, "/");
		strcpy(sandbox_lib, "/lib/");
		strcat(sandbox_lib, LIB_NAME);
		if (-1 == stat(sandbox_lib, &sandbox_lib_stat))
		{
			strcpy(sandbox_lib, sandbox_dir);
			strcat(sandbox_lib, LIB_NAME);
		}
		strcpy(sandbox_rc, "/usr/lib/portage/lib/");
		strcat(sandbox_rc, BASHRC_NAME);
		if (-1 == stat(sandbox_rc, &sandbox_rc_stat))
		{
			strcpy(sandbox_rc, sandbox_dir);
			strcat(sandbox_rc, BASHRC_NAME);
		}

		/* verify the existance of required files */
		if (argc < 2)
		{
			printf("Verification of the required files.\n");
		}
		if (-1 == stat(sandbox_lib, &sandbox_lib_stat))
		{
			fprintf(stderr, "Could not open the sandbox library at '%s'.\n", sandbox_lib);
			return -1;
		}
		else if (-1 == stat(sandbox_rc, &sandbox_rc_stat))
		{
			fprintf(stderr, "Could not open the sandbox rc file at '%s'.\n", sandbox_rc);
			return -1;
		}
		else
		{
			/* ensure that the /etc/ld.so.preload file contains an entry for the sandbox lib */
			if (argc < 2)
			{
				printf("Setting up the ld.so.preload file.\n");
			}

			/* check if the /etc/ld.so.preload file exists */
			if (stat("/etc/ld.so.preload", &preload_stat) < 0 &&
				ENOENT == errno)
			{
				/* if not, try to create it and write the path of the sandbox lib to it */
				success = 1;
				preload_file = open("/etc/ld.so.preload", O_WRONLY|O_CREAT, 0644);
				if (preload_file < 0)
				{
					/* if access was denied, warn the user about it */
					if (EACCES == errno)
					{
						preload_adaptable = 0;
						printf(">>> Couldn't adapt the /etc/ld.so.preload file.\n>>> It's possible that not all function calls are trapped\n");
					}
					else
					{
						perror(">>> /etc/ld.so.preload file open");
						success = 0;
					}
				}
				else
				{
					if (flock(preload_file, LOCK_EX) < 0)
					{
						perror(">>> /etc/ld.so.preload file lock");
						success = 0;
					}
					else
					{
						if (write(preload_file, sandbox_lib, strlen(sandbox_lib)) != strlen(sandbox_lib))
						{
							perror(">>> /etc/ld.so.preload file write");
							success = 0;
						}

						if (flock(preload_file, LOCK_UN) < 0)
						{
							perror(">>> /etc/ld.so.preload file unlock");
							success = 0;
						}
					}
					if (close(preload_file) < 0)
					{
						perror(">>> /etc/ld.so.preload file close");
						success = 0;
					}
					pids_file = -1;
				}
				if (0 == success)
				{
					exit(1);
				}
			}
			else
			{
				/* if the /etc/ld.so.preload file exists, try to open it in read/write mode */
				success = 1;
				if (0 == S_ISREG(preload_stat.st_mode))
				{
					perror(">>> /etc/ld.so.preload file is not a regular file");
					success = 0;
				}
				else
				{
					preload_stream = fopen("/etc/ld.so.preload", "r+");
					if (NULL == preload_stream)
					{
						if (EACCES == errno)
						{
							/* if access was denied, warn the user about it */
							preload_adaptable = 0;
							printf(">>> Couldn't adapt the /etc/ld.so.preload file.\n>>> It's possible that not all function calls are trapped\n");
						}
						else
						{
							perror(">>> /etc/ld.so.preload file fopen");
							success = 0;
						}
					}
					else
					{
						preload_file = fileno(preload_stream);
						if (preload_file < 0)
						{
							perror(">>> /etc/ld.so.preload file fileno");
							success = 0;
						}
						else
						{
							if (flock(preload_file, LOCK_EX) < 0)
							{
								perror(">>> /etc/ld.so.preload file lock");
								success = 0;
							}
							else
							{
								/* check if the sandbox library is already present in the /etc/ld.so.preload file */
								while (EOF != fscanf(preload_stream, "%s\n", preload_entry))
								{
									if (NULL != strstr(preload_entry, LIB_NAME))
									{
										preload_lib_present = 1;
										break;
									}
								}
	
								/* if it's not present, add the sandbox lib path to the end of the /etc/ld.so.preload file */
								if (0 == preload_lib_present)
								{
									if (fseek(preload_stream, 0, SEEK_END) < 0)
									{
										perror(">>> /etc/ld.so.preload file fseek");
										success = 0;
									}
									else
									{
										if (write(preload_file, sandbox_lib, strlen(sandbox_lib)) != strlen(sandbox_lib))
										{
											perror(">>> /etc/ld.so.preload file write");
											success = 0;
										}
									}
								}
	
								if (flock(preload_file, LOCK_UN) < 0)
								{
									perror(">>> /etc/ld.so.preload file unlock");
									success = 0;
								}
							}
						}
						if (EOF == fclose(preload_stream))
						{
							perror(">>> /etc/ld.so.preload file fclose");
							success = 0;
						}
						preload_stream = NULL;
						preload_file = -1;
					}
				}
				if (0 == success)
				{
					exit(1);
				}
			}

			/* set up the required environment variables */
			if (argc < 2)
			{
				printf("Setting up the required environment variables.\n");
			}
			argv_bash[2] = sandbox_rc;

			sprintf(pid_string, "%d", getpid());
			strcpy(sandbox_log, LOG_FILE_PREFIX);
			sandbox_log_env = getenv(ENV_SANDBOX_LOG);
			if (sandbox_log_env)
			{
				strcat(sandbox_log, sandbox_log_env);
				strcat(sandbox_log, "-");
			}
			strcat(sandbox_log, pid_string);
			strcat(sandbox_log, LOG_FILE_EXT);
			setenv(ENV_SANDBOX_LOG, sandbox_log, 1);
			strcpy(sandbox_debug_log, DEBUG_LOG_FILE_PREFIX);
			strcat(sandbox_debug_log, pid_string);
			strcat(sandbox_debug_log, LOG_FILE_EXT);
			setenv(ENV_SANDBOX_DEBUG_LOG, sandbox_debug_log, 1);
			home_dir = getenv("HOME");
			
			// drobbins: we need to expand these paths using realpath() so that PORTAGE_TMPDIR
			// can contain symlinks (example, /var is a symlink, /var/tmp is a symlink.)  Without
			// this, access is denied to /var/tmp, hurtin' ebuilds.
			
			realpath(getenv("PORTAGE_TMPDIR"),portage_tmp_dir);
			realpath("/var/tmp",var_tmp_dir);
			realpath("/tmp",tmp_dir);
			
			setenv(ENV_SANDBOX_DIR, sandbox_dir, 1);
			setenv(ENV_SANDBOX_LIB, sandbox_lib, 1);
			setenv("LD_PRELOAD", sandbox_lib, 1);
			if (NULL == getenv(ENV_SANDBOX_DENY))
			{
				setenv(ENV_SANDBOX_DENY, LD_PRELOAD_FILE, 1);
			}
			if (NULL == getenv(ENV_SANDBOX_READ))
			{
				setenv(ENV_SANDBOX_READ, "/", 1);
			}
			if (NULL == getenv(ENV_SANDBOX_WRITE))
			{
				/* these should go into make.globals later on */
				strcpy(sandbox_write_var, "");
                                strcat(sandbox_write_var, "/dev/zero:/dev/fd/:/dev/null:/dev/pts/:/dev/vc/:/dev/tty:/tmp/");
				strcat(sandbox_write_var, ":");
				strcat(sandbox_write_var, "/var/log/scrollkeeper.log");
				strcat(sandbox_write_var, ":");
				strcat(sandbox_write_var, home_dir);
				strcat(sandbox_write_var, "/.gconfd/lock");
				strcat(sandbox_write_var, ":");
				strcat(sandbox_write_var, home_dir);
				strcat(sandbox_write_var, "/.bash_history");
				strcat(sandbox_write_var, ":");
				strcat(sandbox_write_var, "/usr/tmp/conftest");
				strcat(sandbox_write_var, ":");
				strcat(sandbox_write_var, "/usr/lib/conftest");
				strcat(sandbox_write_var, ":");
				strcat(sandbox_write_var, "/usr/tmp/cf");
				strcat(sandbox_write_var, ":");
				strcat(sandbox_write_var, "/usr/lib/cf");
				strcat(sandbox_write_var, ":");
				if (NULL == portage_tmp_dir)
				{
					strcat(sandbox_write_var, tmp_dir);
					strcat(sandbox_write_var, ":");
					strcat(sandbox_write_var, var_tmp_dir);
					strcat(sandbox_write_var, ":");
					strcat(sandbox_write_var, "/tmp/");
					strcat(sandbox_write_var, ":");
					strcat(sandbox_write_var, "/var/tmp/");
				}
				else if (0 == strcmp(sandbox_write_var, "/var/tmp/"))
				{
					strcat(sandbox_write_var, portage_tmp_dir);
					strcat(sandbox_write_var, ":");
					strcat(sandbox_write_var, tmp_dir);
					strcat(sandbox_write_var, ":");
					strcat(sandbox_write_var, "/tmp/");
				}
				else if (0 == strcmp(sandbox_write_var, "/tmp/"))
				{
					strcat(sandbox_write_var, portage_tmp_dir);
					strcat(sandbox_write_var, ":");
					strcat(sandbox_write_var, var_tmp_dir);
					strcat(sandbox_write_var, ":");
					strcat(sandbox_write_var, "/var/tmp/");
				}
				else
				{
					strcat(sandbox_write_var, portage_tmp_dir);
					strcat(sandbox_write_var, ":");
					strcat(sandbox_write_var, tmp_dir);
					strcat(sandbox_write_var, ":");
					strcat(sandbox_write_var, var_tmp_dir);
					strcat(sandbox_write_var, ":");
					strcat(sandbox_write_var, "/tmp/");
					strcat(sandbox_write_var, ":");
					strcat(sandbox_write_var, "/var/tmp/");
				}
				/* */
				setenv(ENV_SANDBOX_WRITE, sandbox_write_var, 1);
			}
			if (NULL == getenv(ENV_SANDBOX_PREDICT))
			{
				/* these should go into make.globals later on */
				strcpy(sandbox_predict_var, "");
				strcat(sandbox_predict_var, home_dir);
				strcat(sandbox_predict_var, "/.");
				strcat(sandbox_predict_var, ":");
				strcat(sandbox_predict_var, "/usr/lib/python2.0/");
				strcat(sandbox_predict_var, ":");
				strcat(sandbox_predict_var, "/usr/lib/python2.1/");
				strcat(sandbox_predict_var, ":");
				strcat(sandbox_predict_var, "/usr/lib/python2.2/");
				setenv(ENV_SANDBOX_PREDICT, sandbox_predict_var, 1);
				/* */
			}
			setenv(ENV_SANDBOX_ON, "1", 0);

			/* if the portage temp dir was present, cd into it */
			if (NULL != portage_tmp_dir)
			{
				chdir(portage_tmp_dir);
			}

			/* adding additional bash arguments */
			for (i = 1; i < argc; i++)
			{
				if (1 == i)
				{
					argv_bash[3] = run_str;
					argv_bash[4] = run_arg;
					strcpy(argv_bash[4], argv[i]);
				}
				else
				{
					strcat(argv_bash[4], " ");
					strcat(argv_bash[4], argv[i]);
				}
			}

			/* set up the required signal handlers */
			signal(SIGHUP, &stop);
			signal(SIGINT, &stop);
			signal(SIGQUIT, &stop);
			signal(SIGTERM, &stop);

			/* this one should NEVER be set in ebuilds, as it is the one
			 * private thing libsandbox.so use to test if the sandbox
			 * should be active for this pid, or not.
			 *
			 * azarah (3 Aug 2002)
			 */
			setenv("SANDBOX_ACTIVE", "armedandready", 1);
			
			/* fork to executing bash */
			if (argc < 2)
			{
				printf("Creating a seperate process the run the shell in.\n");
			}
			bash_pid = fork();

			if (0 == bash_pid)
			{
				/* launch bash */
				execv(argv_bash[0], argv_bash);
			}
			else
			{
				int		wait_pid = 0;

				if (argc < 2)
				{
					printf("The protected environment has been started.\n");
					printf("--------------------------------------------------------------------------------\n");
				}

				/* store his sandbox's bash pid in the global pids file if it has rights to adapt the ld.so.preload file*/
				if (1 == preload_adaptable)
				{
					success = 1;
					if (0 == lstat(PIDS_FILE, &pids_stat) &&
						0 == S_ISREG(pids_stat.st_mode))
					{
						perror(">>> pids file is not a regular file");
						success = 0;
					}
					else
					{
						pids_file = open(PIDS_FILE, O_WRONLY|O_CREAT|O_APPEND, 0644);
						if (pids_file < 0)
						{
							perror(">>> pids file open");
							success = 0;
						}
						else
						{
							if (flock(pids_file, LOCK_EX) < 0)
							{
								perror(">>> pids file lock");
								success = 0;
							}
							else
							{
								sprintf(pid_string, "%d\n", getpid());
								if (write(pids_file, pid_string, strlen(pid_string)) != strlen(pid_string))
								{
									perror(">>> pids file write");
									success = 0;
								}

								if (flock(pids_file, LOCK_UN) < 0)
								{
									perror(">>> pids file unlock");
									success = 0;
								}
							}
							if (close(pids_file) < 0)
							{
								perror(">>> pids file close");
								success = 0;
							}
							pids_file = -1;
						}
					}
					if (0 == success)
					{
						exit(1);
					}
				}

				/* wait until bash exits */
				wait_pid = waitpid(bash_pid, &status, 0);
			}
		}

		cleanup();

		if (argc < 2)
		{
			printf("========================== Gentoo linux path sandbox ===========================\n");
			printf("The protected environment has been shut down.\n");
		}
 		if (0 == stat(sandbox_log, &sandbox_log_stat))
		{
			sandbox_log_presence = 1;
			success = 1;
			sandbox_log_file = open(sandbox_log, O_RDONLY, 0);
			if (sandbox_log_file < 0)
			{
				perror(">>> sandbox log file open");
				success = 0;
			}
			else
			{
				int		i = 0;
				char*	beep_count_env = NULL;
				int		beep_count = 0;
				int		length = 0;
				char	buffer[255];

				printf("\e[31;01m--------------------------- ACCESS VIOLATION SUMMARY ---------------------------\033[0m\n");
				printf("\e[31;01mLOG FILE = \"%s\"\033[0m\n", sandbox_log);
				printf("\n");
				while ((length = read(sandbox_log_file, buffer, sizeof(buffer)-1)) > 0)
				{
					if (length < sizeof(buffer))
					{
						buffer[length] = 0;
					}
					printf("%s", buffer);
				}
				printf("\e[31;01m--------------------------------------------------------------------------------\033[0m\n");
				
				if (close(sandbox_log_file) < 0)
				{
					perror(">>> sandbox log close");
					success = 0;
				}
				
				beep_count_env = getenv(ENV_SANDBOX_BEEP);
				if (beep_count_env)
				{
					beep_count = atoi(beep_count_env);
				}
				else
				{
					beep_count = DEFAULT_BEEP_COUNT;
				}
				for (i = 0; i < beep_count; i++)
				{
					fputc('\a', stderr);
					if (i < beep_count -1)
					{
						sleep(1);
					}
				}
				
			}
			if (0 == success)
			{
				exit(1);
			}
			sandbox_log_file = -1;
		}
		else if (argc < 2)
		{
			printf("--------------------------------------------------------------------------------\n");
		}

		if (status > 0 ||
			1 == sandbox_log_presence)
		{
			return 1;
		}
		else
		{
			return 0;
		}
	}
}
