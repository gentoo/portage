all: xhtml xhtml-nochunks

XMLTO_FLAGS_man = -x custom.xsl
man pdf txt xhtml xhtml-nochunks:
	xmlto $@ $(XMLTO_FLAGS_$@) portage.docbook

clean distclean:
	rm -f *.1 *.html

.PHONY: all clean distclean \
        man pdf txt xhtml xhtml-nochunks
