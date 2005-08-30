/* $Id: /var/cvsroot/gentoo-src/portage/src/sandbox/problems/Attic/sandbox_dev_fd_foo.c,v 1.2 2003/03/22 14:24:38 carpaski Exp $ */

#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>

void cleanup_1(void)
{
    puts("Unlinking file...");
    unlink("/tmp/_sandbox_test.file");
}

int main(void)
{
    struct stat s1, s2;
    FILE *fp1, *fp2;
    char *file = "/tmp/_sandbox_test.file";
    char devfd[32];

    printf("Opening file...\n");
    if (!(fp1 = fopen(file, "w")))
        exit(1);
    atexit(cleanup_1);
    printf("fstat'ing file...\n");
    if (fstat(fileno(fp1), &s1) < 0)
        exit(2);
    sprintf(devfd, "/dev/fd/%d", fileno(fp1));
    printf("fopening %s...\n", devfd);
    if (!(fp2 = fopen(devfd, "w")))
        exit(3);
    printf("fstat'ing %s...\n", devfd);
    if (fstat(fileno(fp2), &s2) < 0)
        exit(4);
    printf("Checking %ld == %ld and %ld == %ld...\n",
          (long int) s1.st_dev, (long int) s2.st_dev, s1.st_ino, s2.st_ino);
    if (s1.st_dev != s2.st_dev || s1.st_ino != s2.st_ino)
        exit(5);
    printf("Success!\n");
    return(0);
}
