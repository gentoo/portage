/* Copyright Gentoo Foundation 2006-2010
 * Author: Fabian Groffen <grobian@gentoo.org>
 *
 * chpathtool replaces a given string (magic) into another (value),
 * thereby paying attention to the original size of magic in order not
 * to change offsets in the file changed.  To achieve this goal, value
 * may not be greater in size than magic, and for binary files, the
 * difference in size between the two is compensated by prepending
 * '/'-characters to value uptil it matches the size of magic.  For text
 * files magic is just replaced with value, with the additional logic
 * that the end of a string is considered to be at the first NULL-byte
 * encountered after magic.  If no such NULL-byte is found, the padding
 * NULL-bytes are silently dropped.  Since this is done on text files,
 * this is likely the case.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <errno.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <dirent.h>
#include <unistd.h>
#ifdef HAVE_ALLOCA_H
#include <alloca.h>
#endif
#ifdef HAVE_UTIME_H
#include <utime.h>
#endif
#include <sys/time.h>
#include <fcntl.h>

/* Don't allocate too much, or you'll be paying for waiting on IO,
 * size -1 to align in memory. */
#define BUFSIZE 8095
/* POSIX says 256 on this one, but I can hardly believe that really is
 * the limit of most popular systems.  XOPEN says 1024, taking that
 * value, hoping it is enough */
#define MAX_PATH 1024

/* structure to track and trace hardlinks */
typedef struct _file_hlink {
	dev_t    st_dev;            /* device inode resides on */
	ino_t    st_ino;            /* inode's number */
	char     path[MAX_PATH];    /* the file's path + name */
	struct _file_hlink* next;   /* pointer to the next in the list */
} file_hlink;

static char *magic;
static char *value;
static size_t magiclen;
static size_t valuelen;
static char quiet;
static file_hlink *hlinks = NULL;

/**
 * Writes padding zero-bytes after the first encountered zero-byte.
 * Returns padding if no zero-byte was seen, or 0 if padding was
 * applied.
 */
static size_t padonwrite(size_t padding, char *buf, size_t len, FILE *fout) {
	char *z;
	if (padding == 0 || (z = memchr(buf, '\0', len)) == NULL) {
		/* cheap case, nothing complicated to do here */
		fwrite(buf, len, 1, fout);
	} else {
		/* found a zero-byte, insert padding */
		fwrite(buf, z - buf, 1, fout);
		/* now pad with zeros so we don't screw up
		 * the positions in the file */
		buf[0] = '\0';
		while (padding > 0) {
			fwrite(buf, 1, 1, fout);
			padding--;
		}
		fwrite(z, len - (z - buf), 1, fout);
	}

	return(padding);
}

/**
 * Searches buf for an occurrence of needle, doing a byte-based match,
 * disregarding end of string markers (zero-bytes), as strstr does.
 * Returns a pointer to the first occurrence of needle in buf, or NULL
 * if not found.  If a partial match is found at the end of the buffer
 * (size < strlen(needle)) it is returned as well.
 */
static char *memstr(const char *buf, const char *needle, size_t len) {
	const char *ret;
	size_t off;
	for (ret = buf; ret - buf < len; ret++) {
		off = 0;
		while (needle[off] != '\0' &&
				(ret - buf) + off < len &&
				needle[off] == ret[off])
		{
			off++;
		}
		if (needle[off] == '\0' || (ret - buf) + off == len)
			return((char *)ret);
	}
	return(NULL);
}

/**
 * Copies the given file to the output file with prefix transformations
 * on the fly.
 */
static int chpath(const char *fi, const char *fo) {
	FILE *fin;
	FILE *fout;
	size_t len;
	size_t pos;
	size_t padding;
	char *tmp;
	char buf[BUFSIZE + 1];
	char firstblock;
	char *lvalue = value;
	size_t lvaluelen = valuelen;

	/* make sure there is a trailing zero-byte, such that strstr and
	 * strchr won't go out of bounds causing segfaults.  */
	buf[BUFSIZE] = '\0';

	fin  = fopen(fi, "r");
	if (fin == NULL) {
		fprintf(stderr, "unable to open %s: %s\n", fi, strerror(errno));
		return(-1);
	}
	fout = fopen(fo, "w");
	if (fout == NULL) {
		fprintf(stderr, "unable to open %s: %s\n", fo, strerror(errno));
		return(-1);
	}

	pos = 0;
	padding = 0;
	firstblock = 1;
	while ((len = fread(buf + pos, 1, BUFSIZE - pos, fin)) != 0 || pos > 0) {
		if (firstblock == 1) {
			firstblock = 0;
			/* examine the bytes we read to judge if they are binary or
			 * text; in case of the latter we can avoid writing ugly
			 * paths with zilions of slashes */
			for (pos = 0; pos < len; pos++) {
				/* this is a very stupid assumption, but I don't know
				 * anything better: if we find a byte that's out of
				 * ASCII character scope, we assume this is binary */
				if ((buf[pos] < ' ' || buf[pos] > '~') &&
						strchr("\t\r\n", buf[pos]) == NULL)
				{
					/* Make sure we don't mess up code, GCC for instance
					 * hardcodes the result of strlen("string") in
					 * object code.  This means we can nicely replace
					 * this string with a shorter NULL-terminated one,
					 * but that won't change the hardcoded output of the
					 * original strlen.  Hence, pad the value with
					 * slashes until it is of same size as magic. */
					lvalue = alloca(sizeof(char) * (magiclen + 1));
					lvaluelen = magiclen;
					snprintf(lvalue, lvaluelen + 1, "%*s",
							(int)magiclen, value);
					tmp = lvalue;
					while (*tmp == ' ')
						*tmp++ = '/';
					break;
				}
			}
			pos = 0;
		}
		len += pos;
		if ((tmp = memstr(buf, magic, len)) != NULL) {
			/* if binary : */
			if (tmp == buf) {
				if (len < magiclen) {
					/* must be last piece */
					padding = padonwrite(padding, buf, len, fout);
					break;
				}
				/* do some magic, overwrite it basically */
				fwrite(lvalue, lvaluelen, 1, fout);
				/* store what we need to correct */
				padding += magiclen - lvaluelen;
				/* move away the magic */
				pos = len - magiclen;
				memmove(buf, buf + magiclen, pos);
				continue;
			} else {
				/* move this bunch to the front */
				pos = len - (tmp - buf);
			}
		} else {
			/* magic is not in here, since memchr also returns a match
			 * if incomplete but at the end of the string, here we can
			 * always read a new block. */
			if (len != BUFSIZE) {
				/* last piece */
				padding = padonwrite(padding, buf, len, fout);
				break;
			} else {
				pos = 0;
				tmp = buf + len;
			}
		}
		padding = padonwrite(padding, buf, len - pos, fout);
		if (pos > 0)
			memmove(buf, tmp, pos);
	}
	fflush(fout);
	fclose(fout);
	fclose(fin);

	if (padding != 0 && quiet == 0) {
		fprintf(stdout, "warning: couldn't find a location to write "
				"%zd padding bytes in %s\n", padding, fo);
	}

	return(0);
}

int dirwalk(char *src, char *srcp, char *trg, char *trgp) {
	DIR *d;
	struct dirent *de;
	struct stat s;
	struct timeval times[2];
#ifndef HAVE_UTIMES
	struct utimbuf ub;
#endif
	char *st;
	char *tt;

	if (lstat(trg, &s) != 0) {
		/* initially create directory read/writable by owner, set
		 * permissions like src when we're done processing this
		 * directory. */
		if (mkdir(trg, S_IRWXU) != 0) {
			fprintf(stderr, "failed to create directory %s: %s\n",
					trg, strerror(errno));
			return(-1);
		}
	} else {
		fprintf(stderr, "directory already exists: %s\n", trg);
		return(-1);
	}

	if ((d = opendir(src)) == NULL) {
		fprintf(stderr, "cannot read directory %s: %s\n", src, strerror(errno));
		return(-1);
	}
	/* store the end of the string pointer */
	st = srcp;
	tt = trgp;
	while ((de = readdir(d)) != NULL) {
		if (strcmp(de->d_name, "..") == 0 || strcmp(de->d_name, ".") == 0)
			continue;

		*st = '/';
		strcpy(st + 1, de->d_name);
		*tt = '/';
		strcpy(tt + 1, de->d_name);
		st += 1 + strlen(de->d_name);
		tt += 1 + strlen(de->d_name);

		if (lstat(src, &s) != 0) {
			fprintf(stderr, "cannot stat %s: %s\n", src, strerror(errno));
			closedir(d);
			return(-1);
		}
		if (
				S_ISBLK(s.st_mode) ||
				S_ISCHR(s.st_mode) ||
				S_ISFIFO(s.st_mode) ||
#ifdef HAVE_S_ISWHT
				S_ISWHT(s.st_mode) ||
#endif
				S_ISSOCK(s.st_mode)
		   )
		{
			fprintf(stderr, "missing implementation for copying "
					"object %s\n", src);
			closedir(d);
			return(-1);
		} else if (
				S_ISDIR(s.st_mode)
				)
		{
			/* recurse */
			if (dirwalk(src, st, trg, tt) != 0)
				return(-1);
		} else if (
				S_ISREG(s.st_mode)
				)
		{
			/* handle hard links, match each of them to a list of known
			 * files (with st_nlink > 1), such that we only process each
			 * file once, and are able to restore the hard link. */
			if (s.st_nlink > 1) {
				if (hlinks == NULL) {
					hlinks = malloc(sizeof(file_hlink));
					hlinks->st_dev = s.st_dev;
					hlinks->st_ino = s.st_ino;
					strcpy(hlinks->path, src);
					hlinks->next = NULL;
				} else {
					/* look for this file */
					file_hlink *hl = NULL;
					do {
						hl = (hl == NULL ? hlinks : hl->next);
						if (hl->st_dev == s.st_dev && hl->st_ino == s.st_ino) {
							/* this is the same file, make a hard link */
							if (link(hl->path, trg) != 0) {
								fprintf(stderr, "failed to create hard link "
										"%s: %s\n", trg, strerror(errno));
								return(-1);
							}
							hl = NULL;
							break;
						}
					} while (hl->next != NULL);
					/* we didn't know this one yet, add it */
					if (hl != NULL) {
						hl = hl->next = malloc(sizeof(file_hlink));
						hl->st_dev = s.st_dev;
						hl->st_ino = s.st_ino;
						strcpy(hl->path, src);
						hl->next = NULL;
					} else {
						/* don't "copy" the file, we already made a hard
						 * link to it, just restore modified path */
						st = srcp;
						tt = trgp;
						*st = *tt = '\0';
						continue;
					}
				}
			}

			/* copy */
			if (chpath(src, trg) != 0) {
				closedir(d);
				return(-1);
			}
			/* fix permissions */
			if (chmod(trg, s.st_mode) != 0) {
				fprintf(stderr, "failed to set permissions of %s: %s\n",
						trg, strerror(errno));
				return(-1);
			}
			if (chown(trg, s.st_uid, s.st_gid) != 0) {
				fprintf(stderr, "failed to set ownership of %s: %s\n",
						trg, strerror(errno));
				return(-1);
			}
			times[0].tv_sec = s.ATIME_SEC;
#ifdef ATIME_NSEC
			times[0].tv_usec = (s.ATIME_NSEC) / 1000;
#else
			times[0].tv_usec = 0;
#endif
			times[1].tv_sec = s.MTIME_SEC;
#ifdef MTIME_NSEC
			times[1].tv_usec = (s.MTIME_NSEC) / 1000;
#else
			times[1].tv_usec = 0;
#endif
#ifdef HAVE_UTIMES
			if (utimes(trg, times) != 0) {
				fprintf(stderr, "failed to set utimes of %s: %s\n",
						trg, strerror(errno));
				return(-1);
			}
#else
			ub.actime = s.ATIME_SEC;
			ub.modtime = s.MTIME_SEC;
			if (utime(trg, &ub) != 0) {
				fprintf(stderr, "failed to set utime of %s: %s\n",
						trg, strerror(errno));
				return(-1);
			}
#endif
		} else if (
				S_ISLNK(s.st_mode)
				)
		{
			char buf[MAX_PATH];
			char rep[MAX_PATH];
			char *pb = buf;
			char *pr = rep;
			char *p = NULL;
			int len = readlink(src, buf, MAX_PATH - 1);
			buf[len] = '\0';
			/* replace occurences of magic by value in the string if
			 * absolute */
			if (buf[0] == '/') while ((p = strstr(pb, magic)) != NULL) {
				memcpy(pr, pb, p - pb);
				pr += p - pb;
				memcpy(pr, value, valuelen);
				pr += valuelen;
				pb += magiclen;
			}
			len = (&buf[0] + len) - pb;
			memcpy(pr, pb, len);
			pr[len] = '\0';

			if (symlink(rep, trg) != 0) {
				fprintf(stderr, "failed to create symlink %s -> %s: %s\n",
						trg, rep, strerror(errno));
				return(-1);
			}

#ifdef HAVE_LCHOWN
			if (lchown(trg, s.st_uid, s.st_gid) != 0) {
				fprintf(stderr, "failed to set ownership of %s: %s\n",
						trg, strerror(errno));
				return(-1);
			}
#endif
		}

		/* restore modified path */
		st = srcp;
		tt = trgp;
		*st = *tt = '\0';
	}
	closedir(d);

	/* fix permissions/ownership etc. */
	if (lstat(src, &s) != 0) {
		fprintf(stderr, "cannot stat %s: %s\n", src, strerror(errno));
		return(-1);
	}
	if (chmod(trg, s.st_mode) != 0) {
		fprintf(stderr, "failed to set permissions of %s: %s\n",
				trg, strerror(errno));
		return(-1);
	}
	if (chown(trg, s.st_uid, s.st_gid) != 0) {
		fprintf(stderr, "failed to set ownership of %s: %s\n",
				trg, strerror(errno));
		return(-1);
	}
	times[0].tv_sec = s.ATIME_SEC;
#ifdef ATIME_NSEC
	times[0].tv_usec = (s.ATIME_NSEC) / 1000;
#else
	times[0].tv_usec = 0;
#endif
	times[1].tv_sec = s.MTIME_SEC;
#ifdef MTIME_NSEC
	times[1].tv_usec = (s.MTIME_NSEC) / 1000;
#else
	times[1].tv_usec = 0;
#endif
#ifdef HAVE_UTIMES
	if (utimes(trg, times) != 0) {
		fprintf(stderr, "failed to set utimes of %s: %s\n",
				trg, strerror(errno));
		return(-1);
	}
#else
	ub.actime = s.ATIME_SEC;
	ub.modtime = s.MTIME_SEC;
	if (utime(trg, &ub) != 0) {
		fprintf(stderr, "failed to set utime of %s: %s\n",
				trg, strerror(errno));
		return(-1);
	}
#endif

	return(0);
}

int main(int argc, char **argv) {
	struct stat file;
	int o = 0;

	quiet = 0;
	if (argc >= 2 && strcmp(argv[1], "-q") == 0) {
		argc--;
		o++;
		quiet = 1;
	}

	if (argc != 5) {
		fprintf(stderr, "usage: [-q] in-file out-file magic value\n");
		fprintf(stderr, "       if in-file is a directory, out-file is "
				"treated as one too\n");
		fprintf(stderr, " -q  suppress messages about being unable to "
				"write padding bytes\n");
		return(-1);
	}

	magic    = argv[o + 3];
	value    = argv[o + 4];
	magiclen = strlen(magic);
	valuelen = strlen(value);

	if (magiclen < valuelen) {
		fprintf(stderr, "value length (%zd) is bigger than "
				"the magic length (%zd)\n", valuelen, magiclen);
		return(-1);
	}
	if (magiclen > BUFSIZE) {
		fprintf(stderr, "magic length (%zd) is bigger than "
				"BUFSIZE (%d), unable to process\n", magiclen, BUFSIZE);
		return(-1);
	}

	if (lstat(argv[o + 1], &file) != 0) {
		fprintf(stderr, "unable to stat %s: %s\n",
				argv[o + 1], strerror(errno));
		return(-1);
	}
	if (S_ISDIR(file.st_mode)) {
		char *src = alloca(sizeof(char) * MAX_PATH);
		char *trg = alloca(sizeof(char) * MAX_PATH);
		strcpy(src, argv[o + 1]);
		strcpy(trg, argv[o + 2]);
		/* walk this directory and process recursively */
		return(dirwalk(src, src + strlen(argv[o + 1]),
					trg, trg + strlen(argv[o + 2])));
	} else {
		/* process as normal file */
		return(chpath(argv[o + 1], argv[o + 2]));
	}
}

