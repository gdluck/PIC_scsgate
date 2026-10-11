# Replays the firmware corpus through the PIC's own device-table classifier (host build).
CC ?= cc
CFLAGS ?= -std=c99 -O1 -Wall -Wno-unused-variable -Wno-unused-but-set-variable
all: devtab_test
classifier.inc covers.inc: ../../ESPSCSGATE.C extract.py
	python3 extract.py ../../ESPSCSGATE.C classifier.inc
devtab_test: devtab_test.c classifier.inc covers.inc
	$(CC) $(CFLAGS) -o $@ devtab_test.c
test: devtab_test
	./devtab_test ../scs_own/hex2own_corpus.tsv
clean:
	rm -f devtab_test classifier.inc covers.inc
