"""Frames the gateway itself puts on the bus for an OWN request (status / dimension requests).

The firmware never translates these when it *receives* them (they are its own output), so scs_own_all
falls back to this module: generic rules for the request families plus the exact inverse table INV
(body -> OWN) built from the own->hex sweep results by build_tables2.py.
"""
import json, os
_T = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fw_tables.json')))
INV = _T.get('INV', {})
LREQ = {(0x0D, 0x0D): 1, (0x06, 0x00): 2, (0x0D, 0x00): 4, (0x15, 0x00): 5, (0x10, 0x00): 6, (0x16, 0x00): 7,
        (0x17, 0x00): 8, (0x0C, 0x00): 12, (0x0B, 0x00): 14, (0x07, 0x00): 15}        # WHO 1 dimension request codes
TREQ99 = {0x00: 0, 0x0C: 2, 0x0F: 3, 0x0B: 11, 0x12: 12, 0x0D: 13, 0x0E: 14, 0x90: 16, 0x14: 17, 0x13: 19,
          0x10: 20, 0xF1: 27, 0xF2: 28, 0xC3: 30, 0xC4: 31, 0xC5: 32}
TREQD1 = {0x21: 15, 0xCD: 18, 0x17: 21, 0x19: 29, 0x08: 60, 0x01: 4, 0x02: 5, 0x03: 6, 0x05: 7}


def where_from_addr(a):
    A, PL = a >> 4, a & 0x0F
    return "%d%d" % (A, PL) if A < 10 and PL < 10 else "%02d%02d" % (A, PL)


def _thermo_where(z, n):
    if z >= 0x80:
        return "%d#%d" % (z & 0x7F, n) if n else None
    if n:
        return "%d%02d" % (n, z)
    return "%d" % z


def gateway_own(b):
    """body bytes -> list of OWN requests that produce this frame ([] if unknown)"""
    b = bytes(b)
    hit = INV.get(b.hex().upper())
    if hit:
        return list(hit)
    if len(b) == 4:
        c, a, s, v = b
        if s == 0x15 and v == 0:                                         # WHO 1 / 2 status request (same frame for both)
            if c < 0xB0: return ["*#1*%s##" % where_from_addr(c)]
            if c == 0xB1 and a == 0: return ["*#1*0##"]
            if c == 0xB3: return ["*#1*%d##" % a]
            if c == 0xB5: return ["*#1*#%d##" % a]
        if c == 0x99 and s >> 4 == 3:                                    # WHO 4 requests
            n = s & 0x0F
            if v == 0xC0 and a < 0x80:
                return ["*#4*#0##" if a == 0 else "*#4*#0#%d##" % a]
            w = _thermo_where(a, n)
            if w is not None and v in TREQ99:
                return ["*#4*%s*%d##" % (w, TREQ99[v])]
        if c == 0xA9 and s == 0x30 and v == 0x10: return ["*#4*%d*20##" % a]
        if c == 0xB9 and a == 0 and s == 0x30 and v == 0x10: return ["*#4*#0*20##"]
        return []
    if len(b) == 8:
        h, aa, bb, cmd, d, v1, v2, v3 = b
        if h in (0xD1, 0xD2, 0xD5) and cmd == 0x43 and (d, v1) in LREQ and v2 == 0 and v3 == 0 and bb & 0x0F == 1:
            dim = LREQ[(d, v1)]; i = bb >> 4
            ifs = "#4#%02d" % i if i else ""
            if h == 0xD1: w = where_from_addr(aa) + ifs
            elif h == 0xD2: w = "0" + ifs if aa == 0 else None
            else: w = ("#%d" % (aa & 0x0F) if bb & 0x10 == 0 else "%d" % (aa & 0x0F)) + ("#4#%02d" % (aa >> 4) if aa >> 4 else "")
            return ["*#1*%s*%d##" % (w, dim)] if w else []
        if h == 0xD1 and cmd == 0x03 and (bb & 0x0F) == 3 and d in TREQD1 and v1 == v2 == v3 == 0:
            w = _thermo_where(aa, bb >> 4)
            return ["*#4*%s*%d##" % (w, TREQD1[d])] if w else []
        if h == 0xD2 and aa == 0 and bb == 0x03 and cmd == 0x03 and d in TREQD1 and v1 == v2 == v3 == 0:
            return ["*#4*0*%d##" % TREQD1[d]]
        if h == 0xD1 and aa == 0 and bb == 0x03 and cmd == 0x03 and d == 0xC2 and v2 == v3 == 0:
            return ["*#4*#%d##" % v1]
    return []
