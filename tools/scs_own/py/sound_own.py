"""WHO 22 (sound diffusion) OWN -> SCS, from bt_multi (mhs1) sweeps (multi.tsv). WHO 16 is not handled by bt_multi."""
import re

# WHAT -> value byte of the short "command" frame (type nibble 4)
CMD_VAL = {3: 0x01, 4: 0x11, 5: 0xA0, 6: 0xB0, 9: 0xC1, 10: 0xD1, 11: 0xC1, 12: 0xD1, 13: 0xE0}
CMD_VAL_N = {(14, 0): 0xE1, (17, 1): 0xE4}                       # WHAT#N
STEP_VAL = {1: 0xF0, 2: 0xF1}                                    # *22*1#N -> type nibble 0, value F0/F1
REQ_VAL = {1: 0x00, 5: 0xA0, 6: 0xC0, 11: 0xA0, 12: 0x8F}        # *#22*W*DIM## short request (type nibble 5)
REQ_EXT = {2: 0x07, 4: 0x07, 17: 0x08, 18: 0x0C, 19: 0x0C, 20: 0x0C, 25: 0x0F}   # ext request  ..33 code


def parse_where(w):
    """'Z#S[#L]' -> (zone, source, level) ints or None"""
    p = w.split('#')
    if not all(x.isdigit() for x in p) or len(p) not in (2, 3):
        return None
    z, s = int(p[0]), int(p[1])
    l = int(p[2]) if len(p) == 3 else None
    return z, s, l


def frame_addr(z, s, l):
    """-> (prefix, b1, b2, type_hi, ext_hdr) ; ext_hdr = (h, b1, b2) for extended frames"""
    if z == 1:
        return None, 0x00, 0x8F, 0x90, (0xD1, 0x00, 0xF8)
    if z == 2 and l is None:
        return None, s, 0x8F, 0x90, (0xD1, s, 0xF8)
    if z == 2:
        return [0xE0 | l, 0, 0, 0], s, 0x8F, 0x90, (0xD3, s, 0xF8, l)
    if z == 3 and l is not None:
        return None, l, 0x80 | s, 0x90, (0xD1, l, (s << 4) | 0x08)
    if z == 5 and l is not None:
        return None, l, 0x8F, 0xB0, (0xD2, l, 0xF8)
    return None


def own_to_scs(msg):
    m = msg.strip(); f = m.strip('*#').split('*')
    if len(f) < 3:
        return []
    if m.startswith('*22*'):
        what, where = f[1], f[2]
        pw = parse_where(where)
        if pw is None:
            return []
        fa = frame_addr(*pw)
        if fa is None:
            return []
        pre, b1, b2, thi, ext = fa
        lvl = ext[3] if len(ext) == 4 else 3                      # D3 frames carry the level in the type nibble
        ext = ext[:3]
        parts = what.split('#')
        if not all(x.isdigit() for x in parts):
            return []
        w = int(parts[0])
        body = None
        if len(parts) == 1 and w in CMD_VAL:
            v = CMD_VAL[w]
            if w in (3, 4):                                       # low nibble carries the level (0 for zone 1)
                v = (v & 0xF0) | (0 if pw[0] == 1 else (pw[2] if pw[0] in (3, 5) and pw[2] is not None else 1))
            body = [thi | 0x04, b1, b2, v]
        elif len(parts) == 2 and (w, int(parts[1])) in CMD_VAL_N:
            body = [thi | 0x04, b1, b2, CMD_VAL_N[(w, int(parts[1]))]]
        elif len(parts) == 2 and w == 1 and int(parts[1]) in STEP_VAL:
            v = STEP_VAL[int(parts[1])] if pw[0] != 3 else ((pw[1] << 4) | (int(parts[1]) - 1))
            body = [thi | 0x00, b1, b2, v]
        elif len(parts) == 3 and parts[1] == '4' and w in (0, 1, 2, 23) and 1 <= int(parts[2]) <= 8:   # *22*W#4#N: source switching
            body = [{0: thi | 0x01, 1: 0x90, 2: thi | 0x02, 23: thi | 0x0A}[w], b1, b2, (int(parts[2]) << 4) | 0x03]
            if w == 1 and pw[0] == 5:
                body[0] = 0x90
        elif len(parts) == 1 and w in (31, 32):
            h, e1, e2 = ext
            body = [h, e1, e2, (lvl << 4) | 0x05, 0x01, 0x40 + (w - 30), 0x04, 0x00]
        elif len(parts) == 2 and w == 36 and parts[1] == '1':
            h, e1, e2 = ext
            body = [h, e1, e2, (lvl << 4) | 0x02, 0x07, 0xC0, 0xC0, 0x41]
        if body is None:
            return []
        return [(pre + body) if (pre and len(body) == 4) else body]
    if m.startswith('*#22*'):
        where, rest = f[1], f[2:]
        pw = parse_where(where)
        if pw is None or not rest:
            return []
        fa = frame_addr(*pw)
        if fa is None:
            return []
        pre, b1, b2, thi, ext = fa
        lvl = ext[3] if len(ext) == 4 else 3
        h, e1, e2 = ext[:3]
        t3, t2, t4 = (lvl << 4) | 3, (lvl << 4) | 2, (lvl << 4) | 4
        d = rest[0]; a = rest[1:]
        if not d.lstrip('#').isdigit():
            return []
        dim = int(d.lstrip('#'))
        if not d.startswith('#'):
            if a:                                                 # state forms (what a source reports), taken as-is
                ints = [int(x) for x in a] if all(x.isdigit() for x in a) else None
                if ints is None:
                    return []
                if dim == 1 and len(ints) == 1 and ints[0] <= 255:
                    return [[thi | 0x06, b1, b2, ints[0]]]
                if dim == 6 and len(ints) == 1:
                    return [[thi | 0x06, b1, b2, 0xC0]]
                if dim == 12 and len(ints) == 2:
                    return [[thi | 0x06, b1, b2, 0x8F if ints[0] == 0 else 0x80 | ((ints[1] - 1) & 0x0F)]]
                t34 = t4
                if dim == 17 and len(ints) == 1:
                    return [[h, e1, e2, t34, 0x08, 0, 0, 0]]
                if dim == 18 and len(ints) == 1:
                    return [[h, e1, e2, t34, 0x0C, 0x30, 0, 0]]
                if dim == 19 and len(ints) == 1:
                    return [[h, e1, e2, t34, 0x0C, 0x33, 0, ints[0] & 0xFF]]
                if dim == 20 and len(ints) == 1:
                    return [[h, e1, e2, t34, 0x0C, 0x13, 0, 0x80]]
                if dim == 2 and len(ints) == 1:
                    return [[h, e1, e2, t34, 0x07, ints[0] & 0xFF, 0xC0, 0xC0]]
                if dim == 4 and len(ints) == 1:
                    return [[h, e1, e2, t34, 0x07, 0xC0, 0xC0, ints[0] & 0xFF]]
                if dim == 10 and len(ints) >= 1:                  # RDS text: only the first character travels
                    return [[h, e1, e2, 0x35, 0x01, 0xC0, 0x02, ints[0] & 0xFF]]
                if dim == 11 and len(ints) == 3:
                    fq = int(ints[1] * 0.8)
                    return [[h, e1, e2, t34, 0x02, ints[2] & 0xFF, fq >> 8, fq & 0xFF]]
                if dim == 5 and len(ints) == 2:
                    fq = int(ints[1] * 0.8)
                    return [[h, e1, e2, t34, 0x02, 0x0F, fq >> 8, fq & 0xFF]]
                return []
            if dim in REQ_VAL:
                body = [thi | 0x05, b1, b2, REQ_VAL[dim]]
                return [(pre + body) if pre else body]
            if dim in REQ_EXT:
                return [[h, e1, e2, t3, REQ_EXT[dim], 0, 0, 0]]
            return []
        if dim == 1 and len(a) == 1 and a[0].isdigit() and int(a[0]) <= 31:
            body = [thi | 0x03, b1, b2, int(a[0])]
            return [(pre + body) if pre else body]
        if dim == 2 and len(a) == 1 and a[0].isdigit() and int(a[0]) <= 10:
            return [[h, e1, e2, t2, 0x07, int(a[0]), 0xC0, 0xC0]]
        if dim == 5 and a == ['1']:
            return [[h, e1, e2, t2, 0x02, 0x0F, 0x00, 0x00]]
        return []
    return []
