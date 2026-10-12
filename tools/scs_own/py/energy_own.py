"""WHO 18 (energy management) OWN -> SCS, from bt_supervisione (mhs1) sweeps (sup_own2scs.tsv, ext18.tsv)."""
import re

REQ = {51: (0x50, 0x15), 53: (0x50, 0x17), 54: (0x50, 0x18), 71: (0x70, 0x03), 72: (0x70, 0x04),
       73: (0x70, 0x05), 11: (0x00, 0x11), 113: (0x00, 0x1D), 120: (0x00, 0x24)}
REQN = {510: 0x14, 511: 0x1A, 512: 0x1B, 513: 0x1C, 514: 0x1D, 52: 0x16}   # *#18*W*dim#a[#b]## -> 50 code a b
CMD33 = {53: 0x11, 54: 0x12, 55: 0x13, 56: 0x14, 57: 0x1A, 58: 0x1B, 59: 0x1C, 510: 0x1D}
CMD32 = {71: (0x70, 0x01, 0x00), 72: (0x70, 0x01, 0x00), 73: (0x70, 0x02, 0xFF), 74: (0x70, 0x02, 0x00),
         75: (0x70, 0x04, 0x00), 51: (0x50, 0x01, 0x00)}
HI = {1: 0x00, 3: 0x80, 5: 0xA0, 7: 0xB0}          # first digit of WHERE -> high part of the address byte


def addr(where):
    """WHERE -> (address byte, header byte 3) or None. '1', 'XY', 'XY#0' (7Y needs #0)."""
    m = re.fullmatch(r'(\d{1,3})(#0)?', where)
    if not m:
        return None
    w, act = m.group(1), m.group(2) is not None
    if w == '1' and not act:
        return 0x00, 0x02
    if w == '5' and not act:
        return 0xA0, 0x02
    if len(w) == 3:
        return (int(w[1:]), 0x02) if w[0] == '1' and not act else None
    if len(w) == 2 and int(w[0]) in HI:
        if w[0] == '7':
            return (0xB0 | int(w[1]), 0x12) if act else None
        return HI[int(w[0])] | int(w[1]), 0x02
    return None


def own_to_scs(msg):
    m = msg.strip(); f = m.strip('*#').split('*')
    if m.startswith('*18*') and len(f) >= 3:
        what, where = f[1], f[2]
        a = addr(where)
        if a is None:
            return []
        parts = what.split('#')
        if not parts[0].isdigit():
            return []
        w = int(parts[0]); n = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else None
        if len(parts) > 2:
            return []
        if w in CMD33 and (n is None or n <= 255):
            return [[0xD1, a[0], a[1], 0x33, 0x50, CMD33[w], n or 0, 0]]
        if w in CMD32 and n is None:
            hi, c, b = CMD32[w]
            return [[0xD1, a[0], a[1], 0x32, hi, c, b, 0]]
        return []
    if m.startswith('*#18*') and len(f) >= 3:
        where, rest = f[1], f[2:]
        a = addr(where)
        if a is None:
            return []
        d = rest[0]
        if d == '#1200#1' and len(rest) >= 2 and rest[1].isdigit() and int(rest[1]) <= 255:
            return [[0xD1, a[0], a[1], 0x32, 0x00, 0x02, 0x1D, int(rest[1])]]
        parts = d.split('#')
        if not parts[0].isdigit():
            return []
        dim = int(parts[0]); sub = parts[1:]
        if dim in REQN and len(sub) == (2 if dim in (511, 52) else 1) and all(x.isdigit() and int(x) <= 255 for x in sub):
            b = [int(x) for x in sub] + [0]
            return [[0xD1, a[0], a[1], 0x33, 0x50, REQN[dim], b[0], b[1]]]
        if dim in REQ and not sub:
            hi, lo = REQ[dim]
            return [[0xD1, a[0], a[1], 0x33, hi, lo, 0, 0]]
    return []
