#!/usr/bin/env python3
"""Extract the device-table classifier from ESPSCSGATE.C (OutputMapping) into classifier.inc, and the
area cover command (CmdGruppoTapparelle) into covers.inc.

The classifier block starts at the short-frame parse ("if ((scsMessageRx[rBufferIdxR][0] == 7) &&") and
ends after the extended-frame block, so the host test compiles the same lines the PIC runs.
"""
import sys, pathlib
src = pathlib.Path(sys.argv[1]).read_text(encoding='latin-1')
out = pathlib.Path(sys.argv[2])
start = src.index('\t\t\t\t  if ((scsMessageRx[rBufferIdxR][0] == 7) &&')
end_marker = '\t\t\t\t  } //  switch (scsMessageRx[rBufferIdxR][4]\n'
end = src.index(end_marker) + len(end_marker)
# include the extended-frame block that follows the switch
tail = src.index('\t\t\t\t} //  if sm_stato   !=  SM_TEST_MODE) &&', end)
block = src[start:tail]
out.write_text(block, encoding='latin-1')
print('extracted %d lines into %s' % (block.count('\n'), out))

fstart = src.index('void CmdGruppoTapparelle(BYTE area, BYTE comando)\n{')
fend = src.index('\n}\n', fstart) + 3
cov = out.with_name('covers.inc')
cov.write_text(src[fstart:fend], encoding='latin-1')
print('extracted %d lines into %s' % (src[fstart:fend].count('\n'), cov))
