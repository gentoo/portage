SUBDIRS = src man bin pym cnf

AUTOMAKE_OPTIONS = dist-bzip2 no-dist-gzip

BUILT_SOURCES = subst-install.vars

subst-install: subst-install.vars

#
# shells vary interpreting backslash within single quote: echo '\\'
# bourne shell: \
#         bash: \\
#
subst-install.vars: subst-install.vars.in
	@rm -f $@ \
	; case `echo '\\'` in \
	  \\) bss='\\\\\\\\';; \
	  \\\\) bss='\\\\';; \
	  *) echo "unknown shell escape behaviour"; exit 1 ;; \
	  esac \
	; { echo; sed -e "s,"'\\'"\",\",g" \
			-e "s,\\\\,$${bss},g" \
			-e "s,#,\\\\\\#,g" \
			-e "s,\","'\\'"\",g" \
		< subst-install.vars.in \
	  ; echo "$@:" \
	  ; echo "	@echo 'creating \$$@'" \
	  ; echo "	@{ \\" \
	  ; eval `grep '^all_configurevars=' $@.in` \
	  ; for v in `echo $${all_configurevars}` all_configurevars \
	  ; do echo "	echo $${v}='\"\$$($${v})\"' ; \\" \
	  ; done \
	  ; echo "	} > \$$@" \
	; } \
	| ${MAKE} -f - $@

distclean-local:
	rm -f subst-install.vars

MAINTAINERCLEANFILES = subst-install.vars.in.in \
	Makefile.in config.guess config.sub configure ltmain.sh aclocal.m4
