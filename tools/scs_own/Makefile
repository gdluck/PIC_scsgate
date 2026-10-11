# C port of the firmware-derived SCS -> OpenWebNet translator (host build).
CC ?= cc
CFLAGS ?= -std=c99 -O2 -Wall

all: scs_own_test

scs_own_test: scs_own.c scs_own.h scs_own_tables.h
	$(CC) $(CFLAGS) -DSCS_OWN_MAIN -o $@ scs_own.c

test: scs_own_test
	./scs_own_test hex2own_corpus.tsv

scs_own_tables.h: py/fw_tables.json gen_c_tables.py
	python3 gen_c_tables.py

clean:
	rm -f scs_own_test
