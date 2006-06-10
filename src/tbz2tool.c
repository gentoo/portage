/* $Id$ */

#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

/*buffered reading/writing size*/
#define BUFLEN 262144 
char *myname="tbz2tool";
struct stat *mystat=NULL;
void *mybuf;
FILE *datafile, *dbfile, *outfile, *infile;
unsigned char endbuf[8];
long seekto,insize;

int exists(const char *myfile) {
	int result;
	result=stat(myfile,mystat);
	if (result==-1)
		return 0;
	return 1;
}

void writefile(FILE *src, FILE *dest) {
	int count=1;
	while (count) {
		count=fread(mybuf, 1, BUFLEN, src);
		fwrite(mybuf, 1, count, dest);
	}
}

void writefileto(FILE *src, FILE *dest, int endpos) {
	int pos=ftell(src);
	int thiscount;
	while (pos < endpos) {
		/* thiscount=how much to read */
		thiscount=endpos-pos;
		if (thiscount>BUFLEN)
			thiscount=BUFLEN;
		thiscount=fread(mybuf, 1, thiscount , src);
		/* thiscount=how much we actually did read */
		if (thiscount==0)
			/* eof -- shouldn't happen */
			break;
		/* update internal position counter */
		pos+=thiscount;
		fwrite(mybuf, 1, thiscount, dest);
	}
}

int main(int argc, char **argv) {
	if ((argc==2) && (!(strcmp(argv[1],"--help"))))
		goto usage;
	if (argc!=5) {
		printf("%s: four arguments expected\n",myname);
		goto error;
	}
	if (!(mystat=(struct stat *) malloc(sizeof(struct stat))))
		goto memalloc;
		
	if (!(mybuf=(void *) malloc(BUFLEN))) {
		free(mystat);
		goto memalloc;
	}
	
	/* JOIN MODE */
	if (!(strcmp(argv[1],"join"))) {
	
		/* check if datafile exists */
		if (!(exists(argv[2]))) {
			printf("%s: %s doesn't exist\n",myname,argv[2]);
			free(mystat);
			goto error;
		}
		
		/* check if dbfile exists */
		if (!(exists(argv[3]))) {
			printf("%s: %s doesn't exist\n",myname,argv[3]);
			free(mystat);
			goto error;
		}
		/* create end buffer for later use */
		endbuf[0]=((mystat->st_size) & 0xff000000) >> 24;
		endbuf[1]=((mystat->st_size) & 0x00ff0000) >> 16;
		endbuf[2]=((mystat->st_size) & 0x0000ff00) >> 8;
		endbuf[3]=(mystat->st_size) & 0x000000ff;
		endbuf[4]='S';
		endbuf[5]='T';
		endbuf[6]='O';
		endbuf[7]='P';
	
		/* if outfile exists, unlink first (safer) */
		if (exists(argv[4])) 
			unlink(argv[4]);
		
		/* open datafile for reading */
		if ((datafile=fopen(argv[2],"r"))==NULL) {
			free(mybuf);
			free(mystat);
			printf("%s: Error opening %s\n",myname,argv[2]);
			goto error;
		}
		
		/* open dbfile for reading */
		if ((dbfile=fopen(argv[3],"r"))==NULL) {
			fclose(datafile);
			free(mybuf);
			free(mystat);
			printf("%s: Error opening %s\n",myname,argv[3]);
			goto error;
		}
	
		/* open outfile for writing */
		if ((outfile=fopen(argv[4],"a"))==NULL) {
			fclose(dbfile);
			fclose(datafile);
			free(mybuf);
			free(mystat);
			printf("%s: Error opening %s\n",myname,argv[4]);
			goto error;
		}
	
		writefile(datafile,outfile);
		writefile(dbfile,outfile);
		fwrite(endbuf,1,8,outfile);
		fclose(outfile);
		fclose(dbfile);
		fclose(datafile);
		free(mybuf);
		free(mystat);
		exit(0);	
	
	/* SPLIT MODE */
	} else if (!(strcmp(argv[1],"split"))) {
	
		/* check if infile exists */
		if (!(exists(argv[2]))) {
			printf("%s: %s doesn't exist\n",myname,argv[2]);
			free(mystat);
			goto error;
		}
		
		/* store infile size for later use */

		insize=mystat->st_size;
		
		/* if datafile exists, unlink first (safer) */
		if (exists(argv[3])) 
			unlink(argv[3]);
		
		/* if dbfile exists, unlink first (safer) */
		if (exists(argv[4])) 
			unlink(argv[4]);
	
		/* open infile for reading */
		if ((infile=fopen(argv[2],"r"))==NULL) {
			free(mybuf);
			free(mystat);
			printf("%s: Error opening %s\n",myname,argv[2]);
			goto error;
		}
		
		/* read in end buffer */
		fseek(infile,-8,SEEK_END);	
		fread(endbuf,1,8,infile);
		/* quick end buffer read and verification */
		if ( (endbuf[4]!='S') || (endbuf[5]!='T') || (endbuf[6]!='O') || (endbuf[7]!='P') )	{
			fclose(infile);
			free(mybuf);
			free(mystat);
			printf("%s: %s appears to be corrupt (end buffer invalid)\n",myname,argv[2]);
			goto error;
		}
		
		seekto=0;
		seekto=seekto+endbuf[0]*256*256*256;
		seekto=seekto+endbuf[1]*256*256;
		seekto=seekto+endbuf[2]*256;
		seekto=seekto+endbuf[3];
		
		/* open datafile for writing */
		if ((datafile=fopen(argv[3],"a"))==NULL) {
			fclose(infile);
			free(mybuf);
			free(mystat);
			printf("%s: Error opening %s\n",myname,argv[3]);
			goto error;
		}
	
		/* open dbfile for writing */
		if ((dbfile=fopen(argv[4],"a"))==NULL) {
			fclose(datafile);
			fclose(infile);
			free(mybuf);
			free(mystat);
			printf("%s: Error opening %s\n",myname,argv[4]);
			goto error;
		}

		rewind(infile);
		writefileto(infile,datafile,insize-(seekto+8));
		fseek(infile,-(seekto+8),SEEK_END);
		writefileto(infile,dbfile,insize-8);
		fclose(infile);
		fclose(dbfile);
		fclose(datafile);
		free(mybuf);
		free(mystat);
		exit(0);	
		
	} else {
		free(mybuf);
		free(mystat);
		goto usage;
	}
	
	usage:
	printf("Usage: %s join DATAFILE DBFILE OUTFILE (datafile + dbfile -> outfile)\n       %s split INFILE DATAFILE DBFILE (infile -> datafile + dbfile)\n",myname,myname);
error:
	exit(1);
memalloc:
	printf("%s: memory allocation error\n",myname);
	exit(2);
}
