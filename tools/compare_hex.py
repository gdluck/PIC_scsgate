#!/usr/bin/env python3
"""Compare two Intel HEX images of the PIC_scsgate firmware, region by region.

    compare_hex.py a.hex b.hex [-n 20]

Regions: application 0x0000-0xEFFF (what scsgate_flash.py sends), bootloader 0xF000-0xFFFF,
id/config 0x200000-0x30000F and EEPROM 0xF00000-0xF003FF.  Exit status 0 when the application
region is identical, 1 otherwise.
"""
import argparse, sys

REGIONS = (('application 0000-EFFF', 0x0000, 0xF000), ('bootloader F000-FFFF', 0xF000, 0x10000),
           ('userid/config', 0x200000, 0x300010), ('eeprom', 0xF00000, 0xF00400))

def parse_hex(path):
    mem, ext = {}, 0
    with open(path) as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line: continue
            if not line.startswith(':'): raise ValueError('%s:%d: not an Intel HEX record' % (path, n))
            rec = bytes.fromhex(line[1:])
            if sum(rec) & 0xFF: raise ValueError('%s:%d: record checksum error' % (path, n))
            ln, addr, typ, data = rec[0], int.from_bytes(rec[1:3], 'big'), rec[3], rec[4:-1]
            if ln != len(data): raise ValueError('%s:%d: bad record length' % (path, n))
            if typ == 1: break
            if typ == 4: ext = int.from_bytes(data, 'big') << 16
            elif typ == 2: ext = int.from_bytes(data, 'big') << 4
            elif typ == 0:
                for i, b in enumerate(data): mem[ext + addr + i] = b
    return mem

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('a'); ap.add_argument('b'); ap.add_argument('-n', type=int, default=20, help='differences to list per region')
    args = ap.parse_args()
    a, b = parse_hex(args.a), parse_hex(args.b)
    status = 0
    for name, lo, hi in REGIONS:
        addrs = sorted(x for x in set(a) | set(b) if lo <= x < hi)
        if not addrs:
            print('%-24s empty in both' % name); continue
        diffs = [x for x in addrs if a.get(x, 0xFF) != b.get(x, 0xFF)]
        only_a = sum(1 for x in addrs if x in a and x not in b)
        only_b = sum(1 for x in addrs if x in b and x not in a)
        print('%-24s %5d bytes in A, %5d in B, span %04X-%04X, %d differ' %
              (name, sum(1 for x in addrs if x in a), sum(1 for x in addrs if x in b), addrs[0], addrs[-1], len(diffs)))
        if only_a or only_b: print('%24s   (%d only in A, %d only in B; missing bytes count as FF)' % ('', only_a, only_b))
        for x in diffs[:args.n]:
            print('%24s   %06X: %s -> %s' % ('', x, '%02X' % a[x] if x in a else '--', '%02X' % b[x] if x in b else '--'))
        if len(diffs) > args.n: print('%24s   ... %d more' % ('', len(diffs) - args.n))
        if diffs and lo == 0: status = 1
    sys.exit(status)

if __name__ == '__main__':
    main()
