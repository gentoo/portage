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
**  $Id: /var/cvsroot/gentoo-src/portage/src/sandbox-dev/Attic/sandbox.c,v 1.4 2002/10/20 21:37:30 azarah Exp $
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
#include <fcntl.h>
#include "sandbox.h"

int preload_adaptable = 1;
int cleaned_up = 0;
int print_debug = 0;

/* Read pids file, and load active pids into an array.  Return number of pids in array */
int load_active_pids(int fd, int **pids)
{
  char *data = NULL;
  char *ptr = NULL, *ptr2 = NULL;
  int my_pid;
  int num_pids = 0;
  long len;

  pids[0] = NULL;

  len = file_length(fd);

  /* Allocate and zero datablock to read pids file */
  data = (char *)malloc((len + 1)*sizeof(char));
  memset(data, 0, len + 1);

  /* Start at beginning of file */
  lseek(fd, 0L, SEEK_SET);

  /* read entire file into a buffer */
  read(fd, data, len);

  ptr = data;

  /* Loop and read all pids */
  while (1) {
    /* Find new line */
    ptr2 = strchr(ptr, '\n');
    if (ptr2 == NULL) break; /* No more PIDs */

    /* clear the \n. And  ptr  should have a null-terminated decimal string */
    ptr2[0] = 0;

    my_pid = atoi(ptr);

    /* If the PID is still alive, add it to our array */
    if ((0 != my_pid) && (0 == kill(my_pid, 0))) {
      pids[0] = (int *)realloc(pids[0], (num_pids + 1)*sizeof(int));
      pids[0][num_pids] = my_pid;
      num_pids++;
    }

    /* Put ptr past the NULL we just wrote */
    ptr = ptr2 + 1;
  }

  if (data) free(data);
  
  return num_pids;
}

/* Read ld.so.preload file, and loads dirs into an array.  Return number of entries in array */
int load_preload_libs(int fd, char ***preloads)
{
  char *data = NULL;
  char *ptr = NULL, *ptr2 = NULL;
  int num_entries = 0;
  long len;

  preloads[0] = NULL;

  len = file_length(fd);

  /* Allocate and zero datablock to read pids file */
  data = (char *)malloc((len + 1)*sizeof(char));
  memset(data, 0, len + 1);

  /* Start at beginning of file */
  lseek(fd, 0L, SEEK_SET);

  /* read entire file into a buffer */
  read(fd, data, len);

  ptr = data;

  /* Loop and read all pids */
  while (1) {
    /* Find new line */
    ptr2 = strchr(ptr, '\n');

    /* clear the \n. And  ptr  should have a null-terminated decimal string
     * Don't break from the loop though because the last line may not
     * terminated with a \n
     */
    if (NULL != ptr2) ptr2[0] = 0;

    /* If listing does not match our libname, add it to the array */
    if ((strlen(ptr)) && (NULL == strstr(ptr, LIB_NAME))) {
      preloads[0] = (char **)realloc(preloads[0], (num_entries + 1)*sizeof(char **));
      preloads[0][num_entries] = strdup(ptr);
      num_entries++;
    }

    if (NULL == ptr2) break; /* No more PIDs */

    /* Put ptr past the NULL we just wrote */
    ptr = ptr2 + 1;
  }
  
  if (data) free(data);

  return num_entries;
}


void cleanup()
{
  int i = 0;
  int success = 1;
  int pids_file = -1, num_of_pids = 0;
  int *pids_array = NULL;
  char pid_string[255];
#ifdef USE_LD_SO_PRELOAD
  int preload_file = -1, num_of_preloads = 0;
  char preload_entry[255];
  char **preload_array = NULL;
#endif


  /* remove this sandbox's bash pid from the global pids
   * file if it has rights to adapt the ld.so.preload file */
  if ((1 == preload_adaptable) && (0 == cleaned_up)) {
    cleaned_up = 1;
    success = 1;

	if (print_debug) printf("Cleaning up pids file.\n");

    /* Stat the PIDs file, make sure it exists and is a regular file */
    if (file_exist(PIDS_FILE, 1) <= 0) {
      perror(">>> pids file is not a regular file");
      success = 0;
      /* We should really not fail if the pidsfile is missing here, but
       * rather just exit cleanly, as there is still some cleanup to do */
      return;
    }

    pids_file = file_open(PIDS_FILE, "r+", 0);
    if (-1 == pids_file) {
      success = 0;
      /* Nothing more to do here */
      return;
    }

    /* Load "still active" pids into an array */
    num_of_pids = load_active_pids(pids_file, &pids_array);
    //printf("pids: %d\r\n", num_of_pids);

#ifdef USE_LD_SO_PRELOAD
    /* clean the /etc/ld.so.preload file if no other sandbox
	 * processes are running anymore */
    if (1 == num_of_pids) {
      success = 1;

      if (print_debug) printf("Cleaning up /etc/ld.so.preload.\n");
	  
      preload_file = file_open("/etc/ld.so.preload", "r+", 0);
      if (-1 != preload_file) {
        /* Load all the preload libraries into an array */
        num_of_preloads = load_preload_libs(preload_file, &preload_array);
        //printf("num preloads: %d\r\n", num_of_preloads);
	/* Clear file */
        file_truncate(preload_file);

        /* store the other preload libraries back into the /etc/ld.so.preload file */
        if(num_of_preloads > 0) {
          for (i = 0; i < num_of_preloads; i++) {
            sprintf(preload_entry, "%s\n", preload_array[i]);
            if (write(preload_file, preload_entry, strlen(preload_entry)) != strlen(preload_entry)) {
              perror(">>> /etc/ld.so.preload file write");
              success = 0;
              break;
            }
          }
        }

	/* Free memory used to store preload array */
        for (i = 0; i < num_of_preloads; i++) {
          if (preload_array[i]) free(preload_array[i]);
          preload_array[i] = NULL;
        }
        if (preload_array) free(preload_array);
        preload_array = NULL;

        file_close(preload_file);
        preload_file = -1;
      }
    }
#endif

    file_truncate(pids_file);

    /* if pids are still running, write only the running pids back to the file */
    if(num_of_pids > 1) {
      for (i = 0; i < num_of_pids; i++) {
        sprintf(pid_string, "%d\n", pids_array[i]);
        if (write(pids_file, pid_string, strlen(pid_string)) != strlen(pid_string)) {
          perror(">>> pids file write");
          success = 0;
          break;
        }
      }

      file_close(pids_file);
      pids_file = -1;
    } else {
            
      file_close(pids_file);
      pids_file = -1;

      /* remove the pidsfile, as this was the last sandbox */
      unlink(PIDS_FILE);
    }

    if (pids_array != NULL) {
      free(pids_array);
      pids_array = NULL;
    }
  }

  if (0 == success) {
    return;
  }
}

void stop(int signum)
{
  printf("Caught signal %d\r\n", signum);
  cleanup();
}

void setenv_sandbox_write(char *home_dir, char *portage_tmp_dir, char *var_tmp_dir, char *tmp_dir)
{
  char sandbox_write_var[1024];

  if (!getenv(ENV_SANDBOX_WRITE)) {
    /* these should go into make.globals later on */
    strcpy(sandbox_write_var, "");
    strcat(sandbox_write_var, "/dev/zero:/dev/fd/:/dev/null:/dev/pts/:/dev/vc/:/dev/tty:/tmp/");
    strcat(sandbox_write_var, ":");
    /* NGPT support */
    strcat(sandbox_write_var, "/dev/shm/ngpt");
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
    if (NULL == portage_tmp_dir) {
      strcat(sandbox_write_var, tmp_dir);
      strcat(sandbox_write_var, ":");
      strcat(sandbox_write_var, var_tmp_dir);
      strcat(sandbox_write_var, ":");
      strcat(sandbox_write_var, "/tmp/");
      strcat(sandbox_write_var, ":");
      strcat(sandbox_write_var, "/var/tmp/");

    /* How the heck is this possible?? we just set it above! */
    } else if (0 == strcmp(sandbox_write_var, "/var/tmp/")) {
      strcat(sandbox_write_var, portage_tmp_dir);
      strcat(sandbox_write_var, ":");
      strcat(sandbox_write_var, tmp_dir);
      strcat(sandbox_write_var, ":");
      strcat(sandbox_write_var, "/tmp/");

    /* Still don't think this is possible, am I just stupid or something? */
    } else if (0 == strcmp(sandbox_write_var, "/tmp/")) {
      strcat(sandbox_write_var, portage_tmp_dir);
      strcat(sandbox_write_var, ":");
      strcat(sandbox_write_var, var_tmp_dir);
      strcat(sandbox_write_var, ":");
      strcat(sandbox_write_var, "/var/tmp/");

    /* Amazing, one I think is possible */
    } else {
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
    
    setenv(ENV_SANDBOX_WRITE, sandbox_write_var, 1);
  }
}


void setenv_sandbox_predict(char *home_dir)
{
  char sandbox_predict_var[1024];

  if (!getenv(ENV_SANDBOX_PREDICT)) {
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
  }
}

int print_sandbox_log(char *sandbox_log)
{
  int sandbox_log_file = -1;
  char *beep_count_env = NULL;
  int i, beep_count = 0;
  long len = 0;
  char *buffer = NULL;

  sandbox_log_file=file_open(sandbox_log, "r", 0);
  if (-1 == sandbox_log_file) {
    return 0;
  }

  len = file_length(sandbox_log_file);
  buffer = (char *)malloc((len + 1)*sizeof(char));
  memset(buffer, 0, len + 1);
  read(sandbox_log_file, buffer, len);
  file_close(sandbox_log_file);

  printf("\e[31;01m--------------------------- ACCESS VIOLATION SUMMARY ---------------------------\033[0m\n");
  printf("\e[31;01mLOG FILE = \"%s\"\033[0m\n", sandbox_log);
  printf("\n");
  printf("%s", buffer);
  if (buffer) free(buffer); buffer = NULL;
  printf("\e[31;01m--------------------------------------------------------------------------------\033[0m\n");

  beep_count_env = getenv(ENV_SANDBOX_BEEP);
  if (beep_count_env) {
    beep_count = atoi(beep_count_env);
  } else {
    beep_count = DEFAULT_BEEP_COUNT;
  }

  for (i = 0; i < beep_count; i++) {
    fputc('\a', stderr);
    if (i < beep_count -1) {
      sleep(1);
    }
  }
  return 1;
}

int spawn_shell(char *argv_bash[]) 
{
#ifdef USE_SYSTEM_SHELL
  int i = 0;
  char *sh = NULL;
  int first = 1;
  int ret;
  long len = 0;

  while (1) {
    if (NULL == argv_bash[i]) break;
    if (NULL != sh) len = strlen(sh);
    sh = (char *)realloc(sh, len+strlen(argv_bash[i]) + 5);
    if (first) {
      sh[0] = 0;
      first = 0;
    }
    strcat(sh, "\"");
    strcat(sh, argv_bash[i]);
    strcat(sh, "\" ");

    //printf("%s\n", argv_bash[i]);
    i++;
  }
  printf("%s\n", sh);
  ret = system(sh);
  if (sh) free(sh);
  sh = NULL;
  
  if (-1 == ret) return 0;
  return 1;
  
#else
# ifndef NO_FORK
  int pid;
  int status = 0;
  int ret = 0;

  pid = fork();

  /* Child's process */
  if (0 == pid) {
# endif
    execv(argv_bash[0], argv_bash);
# ifndef NO_FORK
    return 0;
  } else if (pid < 0) {
    return 0;
  }
  ret = waitpid(pid, &status, 0);
  if ((-1 == ret) || (status > 0)) return 0;
# endif
  return 1;
#endif
}

int main(int argc, char** argv)
{
  int i = 0, success = 1;
  int preload_file = -1;
  int sandbox_log_presence = 0;
  int sandbox_log_file = -1;
  int pids_file = -1;
  long len;

  int *pids_array = NULL;
  int num_of_pids = 0;

  // char run_arg[255];
  char portage_tmp_dir[PATH_MAX];
  char var_tmp_dir[PATH_MAX];
  char tmp_dir[PATH_MAX];
  char sandbox_log[255];
  char sandbox_debug_log[255];
  char sandbox_dir[255];
  char sandbox_lib[255];
  char sandbox_rc[255];
  char pid_string[255];
  char **argv_bash = NULL;

  char *run_str = "-c";
  char *home_dir = NULL;
  char *tmp_string = NULL;
#ifdef USE_LD_SO_PRELOAD
  char **preload_array = NULL;
  int num_of_preloads = 0;
#endif

  /* Only print info if called with no arguments .... */
  if (argc < 2) {
    print_debug = 1;
  }

  if (print_debug) printf("========================== Gentoo linux path sandbox ===========================\n");


  /* check if a sandbox is already running */
  if (NULL != getenv(ENV_SANDBOX_ON)) {
    fprintf(stderr, "Not launching a new sandbox instance\nAnother one is already running in this process hierarchy.\n");
    exit(1);
  } else {

    /* determine the location of all the sandbox support files */
    if (print_debug) printf("Detection of the support files.\n");

    /* Generate base sandbox path */
    tmp_string = get_sandbox_path(argv[0]);
    strncpy(sandbox_dir, tmp_string, 254);
    if (tmp_string) free(tmp_string);
    tmp_string = NULL;
    strcat(sandbox_dir, "/");

    /* Generate sandbox lib path */
    tmp_string = get_sandbox_lib(sandbox_dir);
    strncpy(sandbox_lib, tmp_string, 254);
    if (tmp_string) free(tmp_string);
    tmp_string = NULL;

    /* Generate sandbox bashrc path */
    tmp_string = get_sandbox_rc(sandbox_dir);
    strncpy(sandbox_rc, tmp_string, 254);
    if (tmp_string) free(tmp_string);
    tmp_string = NULL;

    /* verify the existance of required files */
    if (print_debug) printf("Verification of the required files.\n");

    if (file_exist(sandbox_lib, 0) <= 0) {
      fprintf(stderr, "Could not open the sandbox library at '%s'.\n", sandbox_lib);
      return -1;
    } else if (file_exist(sandbox_rc, 0) <= 0) {
      fprintf(stderr, "Could not open the sandbox rc file at '%s'.\n", sandbox_rc);
      return -1;
    }

#ifdef USE_LD_SO_PRELOAD
    /* ensure that the /etc/ld.so.preload file contains an entry for the sandbox lib */
    if (print_debug) printf("Setting up the ld.so.preload file.\n");
#endif

    /* check if the /etc/ld.so.preload is a regular file */
    if (file_exist("/etc/ld.so.preload", 1) < 0) {
      fprintf(stderr, ">>> /etc/ld.so.preload file is not a regular file\n");
      exit(1);
    }

    /* Our r+ also will create the file if it doesn't exist */
    preload_file=file_open("/etc/ld.so.preload", "r+", 1, 0644);
    if (-1 == preload_file) {
      preload_adaptable = 0;
/*      exit(1);*/
    }

#ifdef USE_LD_SO_PRELOAD
    /* Load entries of preload table */
    num_of_preloads = load_preload_libs(preload_file, &preload_array);

    /* Zero out our ld.so.preload file */
    file_truncate(preload_file);

    /* Write contents of preload file */
    for (i = 0; i < num_of_preloads + 1; i++) {
      /* First entry should be our sandbox library */
      if (0 == i) {
        if (write(preload_file, sandbox_lib, strlen(sandbox_lib)) != strlen(sandbox_lib)) {
          perror(">>> /etc/ld.so.preload file write");
          success = 0;
          break;
        }
      } else {
        /* Output all other preload entries */
        if (write(preload_file, preload_array[i - 1], strlen(preload_array[i - 1])) != strlen(preload_array[i - 1])) {
          perror(">>> /etc/ld.so.preload file write");
          success = 0;
          break;
        }
      }
      /* Don't forget the return character after each line! */
      if (1 != write(preload_file, "\n", 1)) {
        perror(">>> /etc/ld.so.preload file write");
        success = 0;
        break;
      }
    }

    for (i = 0; i < num_of_preloads; i++) {
      if (preload_array[i]) free(preload_array[i]);
	  preload_array[i] = NULL;
    }
    if (preload_array) free(preload_array);
    num_of_preloads = 0;
    preload_array = NULL;
#endif

    /* That's all we needed to do with the preload file */
    file_close(preload_file);
    preload_file = -1;
	
    /* set up the required environment variables */
    if (print_debug) printf("Setting up the required environment variables.\n");

    /* Generate sandbox log full path */
    tmp_string=get_sandbox_log();
    strncpy(sandbox_log, tmp_string, 254);
    if (tmp_string) free(tmp_string);
    tmp_string = NULL;

    setenv(ENV_SANDBOX_LOG, sandbox_log, 1);

    snprintf(sandbox_debug_log, 254, "%s%s%s", DEBUG_LOG_FILE_PREFIX, pid_string, LOG_FILE_EXT);
    setenv(ENV_SANDBOX_DEBUG_LOG, sandbox_debug_log, 1);

    home_dir = getenv("HOME");

    /* drobbins: we need to expand these paths using realpath() so that PORTAGE_TMPDIR
     * can contain symlinks (example, /var is a symlink, /var/tmp is a symlink.)  Without
     * this, access is denied to /var/tmp, hurtin' ebuilds.
     */

    realpath(getenv("PORTAGE_TMPDIR"),portage_tmp_dir);
    realpath("/var/tmp",var_tmp_dir);
    realpath("/tmp",tmp_dir);

    setenv(ENV_SANDBOX_DIR, sandbox_dir, 1);
    setenv(ENV_SANDBOX_LIB, sandbox_lib, 1);
    setenv("LD_PRELOAD", sandbox_lib, 1);

    if (!getenv(ENV_SANDBOX_DENY)) {
      setenv(ENV_SANDBOX_DENY, LD_PRELOAD_FILE, 1);
    }

    if (!getenv(ENV_SANDBOX_READ)) {
      setenv(ENV_SANDBOX_READ, "/", 1);
    }

    /* Set up Sandbox Write path */
    setenv_sandbox_write(home_dir, portage_tmp_dir, var_tmp_dir, tmp_dir);
    setenv_sandbox_predict(home_dir);

    setenv(ENV_SANDBOX_ON, "1", 0);

    /* if the portage temp dir was present, cd into it */
    if (NULL != portage_tmp_dir) {
      chdir(portage_tmp_dir);
    }

    argv_bash=(char **)malloc(6 * sizeof(char *));
    argv_bash[0] = strdup("/bin/bash");
    argv_bash[1] = strdup("-rcfile");
    argv_bash[2] = strdup(sandbox_rc);
    if (argc < 2) {
      argv_bash[3] = NULL;
    } else {
      argv_bash[3] = strdup(run_str);  /* "-c" */
    }
    argv_bash[4] = NULL;  /* strdup(run_arg); */
    argv_bash[5] = NULL;
    
    if (argc >= 2) {
      for (i = 1; i< argc; i++) {
        if (NULL == argv_bash[4]) len = 0;
        else len = strlen(argv_bash[4]);
        argv_bash[4]=(char *)realloc(argv_bash[4], (len + strlen(argv[i]) + 2) * sizeof(char));
        if (0 == len) argv_bash[4][0] = 0;
        if (1 != i) strcat(argv_bash[4], " ");
        strcat(argv_bash[4], argv[i]);
      }
    }
#if 0
    char* argv_bash[] = {
                        "/bin/bash",
                        "-rcfile",
                        NULL,
                        NULL,
                        NULL,
                        NULL
                        };
  
    /* adding additional bash arguments */
    for (i = 1; i < argc; i++) {
      if (1 == i) {
        argv_bash[3] = run_str;
        argv_bash[4] = run_arg;
        strcpy(argv_bash[4], argv[i]);
      } else {
        strcat(argv_bash[4], " ");
        strcat(argv_bash[4], argv[i]);
      }
    }
#endif

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


    /* Load our PID into PIDs file if environment is adaptable */
    if (preload_adaptable) {
      success = 1;
      if (file_exist(PIDS_FILE, 1) < 0) {
        success = 0;
        fprintf(stderr, ">>> pids file is not a regular file");
      } else {
        pids_file=file_open(PIDS_FILE, "r+", 1, 0644);
        if (-1 == pids_file) {
        success = 0;
	  } else {
        /* Grab still active pids */
        num_of_pids = load_active_pids(pids_file, &pids_array);

        /* Zero out file */
        file_truncate(pids_file);

        /* Output active pids, and append our pid */
        for (i = 0; i < num_of_pids + 1; i++) {
          /* Time for our entry */
          if (i == num_of_pids) {
            sprintf(pid_string, "%d\n", getpid());
          } else {
            sprintf(pid_string, "%d\n", pids_array[i]);
          }
          if (write(pids_file, pid_string, strlen(pid_string)) != strlen(pid_string)) {
            perror(">>> /etc/ld.so.preload file write");
            success = 0;
            break;
          }
        }
        /* Clean pids_array */
        if (pids_array) free(pids_array);
        pids_array = NULL;
        num_of_pids = 0;

        /* We're done with the pids file */
        file_close(pids_file);
      }
    }

      /* Something went wrong, bail out */
    if (success == 0)
        exit(1);
    }

    /* STARTING PROTECTED ENVIRONMENT */
    if (print_debug) {
      printf("The protected environment has been started.\n");
      printf("--------------------------------------------------------------------------------\n");
    }

    if (print_debug) printf("Shell being started in forked process.\n");

    /* Start Bash */
    if (!spawn_shell(argv_bash)) {
      if (print_debug) fprintf(stderr, ">>> shell process failed to spawn\n");
      success = 0;
    }

    /* Free bash stuff */
    for (i = 0; i < 6; i++) {
      if (argv_bash[i]) free(argv_bash[i]);
	  argv_bash[i] = NULL;
    }
    if (argv_bash) free(argv_bash);
    argv_bash = NULL;

    if (print_debug) {
      printf("Cleaning up sandbox process\n");
    }

    cleanup();

    if (print_debug) {
      printf("========================== Gentoo linux path sandbox ===========================\n");
      printf("The protected environment has been shut down.\n");
    }

    if (file_exist(sandbox_log, 0)) {
      sandbox_log_presence = 1;
      success = 1;
      if (!print_sandbox_log(sandbox_log)) {
        success = 0;
      }

#if 0
      if (!success) {
        exit(1);
      }
#endif
      sandbox_log_file = -1;
    } else if (print_debug) {
      printf("--------------------------------------------------------------------------------\n");
    }

    if ((sandbox_log_presence) || (!success)) {
      return 1;
    } else {
      return 0;
    }
  }
}



// vim:expandtab noai:cindent ai
