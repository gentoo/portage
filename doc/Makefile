all: xhtml xhtml-nochunks

XMLTO_FLAGS = -m custom.xsl
man pdf txt xhtml xhtml-nochunks:
	xmlto $@ $(XMLTO_FLAGS) portage.docbook

clean distclean:
	rm -f *.1 *.html portage.txt

.PHONY: all clean distclean \
        man pdf txt xhtml xhtml-nochunks
