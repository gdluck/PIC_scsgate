#!/usr/bin/env python3
"""Standalone SCS <-> OpenWebNet translator for BTicino thermoregulation (WHO 4).

Every rule and lookup table here was recovered from the device's own translator
(bt_termo in the mhs1 firmware) by running it as an oracle, see SCS_OWN_MAP.md.
No Docker or firmware is needed at runtime.

    python3 scs_own_fw.py hex "A8 D2 28 03 34 12 F0 00 C8 E7 A3"
    python3 scs_own_fw.py own "*4*303*40##"

    from scs_own_fw import scs_to_own, own_to_scs
    scs_to_own("A8 D2 28 03 34 12 F0 00 C8 E7 A3")
        -> ['*#4*40*12*0200*3##', '*4*1*40##']
    own_to_scs("*#4*40*#14*0215*1##") -> ['A8 90 28 30 2B A3 A3']
"""
import re
import sys

# ---------------------------------------------------------------- tables
# status code table, shared by short frames 96/B7 and extended dim 0x13
STAT = {0x00: 1, 0x01: 0, 0x10: 2, 0x11: 3, 0x12: 4, 0x20: 5, 0x21: 6, 0x22: 7,
        0x23: 8, 0x2F: 9, 0x30: 10, 0x31: 11, 0x32: 12, 0x3F: 13, 0x24: 14,
        0x25: 15, 0x26: 16, 0x40: 17, 0x41: 18, 0x42: 19, 0x43: 20, 0x44: 21,
        0x45: 22}
STAT.update({v: 100 + v - 0x80 for v in range(0x80, 0xE5)})

# ext dim 0x12, B1 -> OWN operating mode (*4*MODE*WHERE##)
MODE12 = {0xF0: 1, 0xF1: 0, 0xF2: 102, 0xF3: 202, 0xFF: 303, 0x10: 108,
          0x11: 107, 0x12: 208, 0x13: 207, 0x1B: 408, 0x1C: 407, 0x1D: 402,
          0x1E: 410, 0x1F: 508, 0x20: 507, 0x21: 502, 0x22: 510}

# ext dim 0x05, B1 -> the two fields after *7*
PAIR05 = {0xF0: "1*1", 0xF1: "2*1", 0xF2: "1*2", 0xF3: "2*2", 0xF4: "0*2",
          0xF9: "1*31", 0xFA: "1*32", 0xFF: "0*5", 0x10: "1*3", 0x11: "1*4",
          0x12: "2*3", 0x13: "2*4", 0x14: "3*3", 0x15: "3*4", 0x16: "3*2",
          0x17: "3*1", 0x18: "0*3", 0x19: "0*4", 0x1A: "0*1"}

# ext dim 0x0D, B1 -> value (strings: the firmware zero-pads the first four)
VAL0D = {0x00: "00", 0x0A: "01", 0x14: "02", 0x1E: "03", 0x80: "4", 0x81: "5",
         0x86: "6", 0x82: "7", 0x85: "8", 0xF6: "11", 0xEC: "12", 0xE2: "13"}

# short 93 / 9F command frames
CMD93 = {0x0D: 39, 0x0E: 40}
CMD9F = {0xE0: 41, 0xE1: 42, 0xE2: 43, 0xE5: 44}

# ext DIM byte -> OWN dimension
DIMS = {0x01: 4, 0x02: 5, 0x03: 6, 0x04: 8, 0x05: 7, 0x08: 60, 0x0B: 11,
        0x0C: 2, 0x0D: 13, 0x0E: 14, 0x0F: 3, 0x12: 12, 0x13: 19, 0x14: 17,
        0x16: 22, 0x17: 21, 0x19: 29, 0x21: 15}


# ---------------------------------------------------------------- helpers
def xor(bs):
    x = 0
    for b in bs:
        x ^= b
    return x


def wire(body):
    return "A8 " + " ".join("%02X" % b for b in body) + " %02X A3" % xor(body)


def parse_hex(s):
    """Accept 'A8 .. CHK A3' (A8/B8/D4 start), body+CHK, or bare body."""
    b = bytes.fromhex(re.sub(r"[^0-9A-Fa-f]", "", s))
    if len(b) >= 3 and b[0] in (0xA8, 0xB8, 0xD4) and b[-1] == 0xA3:
        b = b[1:-2]
    elif len(b) in (5, 9) and xor(b[:-1]) == b[-1]:
        b = b[:-1]
    return b


def temp(hi, lo):
    """Firmware '%c%03d' temperature: top nibble = sign digit, 12 bits = tenths."""
    return "%d%03d" % (hi >> 4, (hi & 0x0F) * 256 + lo)


def where_short(z, n, zero="#0"):
    if z >= 0x80:
        return "%d#%d" % (z & 0x7F, n) if n else "%d" % z
    if n:
        return "%d%02d" % (n, z)
    return zero if z == 0 else "%d" % z


# ---------------------------------------------------------------- SCS -> OWN
def scs_to_own(frame):
    """Return the list of OWN messages the firmware emits, or [] if it rejects the frame."""
    b = parse_hex(frame) if isinstance(frame, str) else bytes(frame)
    if len(b) == 4:
        return _short(*b)
    if len(b) == 8:
        return _ext(*b)
    return []


def _short(c, z, s, v):
    if s >> 4 != 3:
        return []
    n = s & 0x0F
    if c in (0xB4, 0xB5) and n != 0x0F:
        w = "%d%02d" % (n, z) if n else "%d" % z
        return ["*#4*%s*0*%04d##" % (w, v + (256 if c == 0xB5 else 0))]
    if c == 0xB7 and v in MODE12 and v >= 0xF0:
        return ["*4*%d*%d##" % (MODE12[v], z)]
    if c in (0x90, 0x91, 0x92):
        return ["*#4*%d*#14*%04d*%d##" % (z, v * 5, c - 0x8F)]
    if c in (0x96, 0xB7) and v in STAT:
        return ["*#4*%s*%s20*%d##" % (where_short(z, n), "#" if c == 0x96 else "", STAT[v])]
    if c in (0x9D, 0x9E):
        val = "" if (c == 0x9E and v == 0xFF) else "#%d" % v
        return ["*4*%s%s*%s##" % ("4001" if c == 0x9D else "4002", val, where_short(z, n))]
    if c == 0x93 and v in CMD93:
        return ["*4*%d*%d##" % (CMD93[v], z)]
    if c in (0x9F, 0xBF) and v in CMD9F:
        return ["*4*%d*%d##" % (CMD9F[v], z)]
    return []


D1_DIMS = {0x01, 0x02, 0x04, 0x05, 0x0B, 0x0C, 0x0F, 0x14, 0x16, 0x17, 0x19}


def _ext(h, z, a, s, dim, b1, b2, b3):
    # D2 = state/answer (bytes 3,4 = x3 x4); D1 = write (bytes 3,4 = x3 02)
    if dim not in DIMS or a & 0x0F != 3:
        return []
    if h == 0xD2 and s & 0x0F == 4:
        pass
    elif h == 0xD1 and s == 0x02 and dim in D1_DIMS:
        pass
    else:
        return []
    d = DIMS[dim]
    n = a >> 4                                       # probe index -> 'N' + '%02d' % zone
    if n and dim not in (0x0D, 0x0E, 0x12, 0x13):
        w = "%d%02d" % (n, z)
    else:
        w = ("#0" if dim != 0x12 else "0") if z == 0 else "%d" % z
    dd = ("#" if h == 0xD1 else "") + str(d)
    pre = "*#4*%s*%s*" % (w, dd)
    if dim in (0x01, 0x02, 0x03, 0x0B):
        return [pre + "%d##" % b1]
    if dim == 0x04:
        return [pre[:-1] + "#%d*%04d##" % (b1 + 1, b2 * 5)]
    if dim == 0x05:
        if b1 not in PAIR05:
            return [pre]                 # firmware emits this truncated string
        if b2 == 0xFF:                   # no set point
            pair = PAIR05[b1] if b1 < 0xF0 or b1 == 0xFF else PAIR05[b1].split("*")[0] + "*0"
            return [pre + pair + "##"]
        return [pre + "%s*%04d##" % (PAIR05[b1], b2 * 5)]
    if dim == 0x08:
        return [pre + "%d##" % b3]
    if dim in (0x0C, 0x0F):
        return [pre + temp(b1, b2) + "##"] if b1 < 0x20 else []
    if dim == 0x0E:
        return [pre + temp(b1, b2) + "*3##"] if b1 < 0x20 else []
    if dim == 0x0D:
        return [pre + VAL0D[b1] + "##"] if b1 in VAL0D else []
    if dim == 0x12:
        if b2 >= 0x20:
            return []
        return [pre + temp(b2, b3) + "*3##", "*4*%d*%s##" % (MODE12.get(b1, -1), w)]
    if dim == 0x13:
        st = lambda x: str(STAT[x]) if x in STAT else ""
        return [pre + "%s*%s##" % (st(b2), st(b1))]
    if dim == 0x14:
        return [pre + "%d*%d*%04d##" % (b1, b2, b3 * 5)]
    if dim == 0x16:
        t = "" if b3 == 0xFF else "%04d" % (b3 * 5)
        hi, lo = b1 >> 4, b1 & 0x0F
        if h == 0xD1:
            lo, tail = str(lo), "*%d" % {0: 1, 1: 0}.get(hi, hi)
        else:
            lo = "" if lo == 0x0F else str(lo)
            tail = {0: "*1", 1: "*0", 0xF: "*"}.get(hi, "")
        return ["*#4*3#%s*%s*%d*%s*%s%s##" % (w, dd, b2, t, lo, tail)]
    if dim == 0x17:
        return [pre + "%d*%d*%d##" % (b1, b2, b3)]
    if dim == 0x19:
        return [pre + "%d*%d*%d##" % (b1, b2, b3)] if (b1 <= 100 or h == 0xD1) else []
    if dim == 0x21:
        wv = b2 * 256 + b3
        return [pre + "%d*%d%03d*%s##" % (b1 & 0x0F, wv >> 15, wv & 0x7FFF,
                                          format(b1 >> 4, "04b"))]
    return []


# ---------------------------------------------------------------- OWN -> SCS
WHAT93 = {1: 0x00, 0: 0x01, 102: 0x02, 202: 0x03, 302: 0x04, 40: 0x0E,
          103: 0x0F, 203: 0x0F, 303: 0x0F}
WHAT9F = {41: 0xE0, 42: 0xE1}
CENTRAL = {1: 0xF0, 102: 0x17, 303: 0x06}
REQ99 = {0: 0x00, 2: 0x0C, 11: 0x0B, 12: 0x12, 13: 0x0D, 14: 0x0E, 19: 0x13,
         30: 0xC3, 31: 0xC4, 32: 0xC5}
REQD1 = {4: 0x01, 5: 0x02, 6: 0x03, 7: 0x05, 15: 0x21, 18: 0xCD, 21: 0x17,
         29: 0x19, 60: 0x08}
M14C = {1: 0x12, 2: 0x22, 3: 0x02}


def _zone(w):
    """plain zone 'Z' -> byte, or 'Z#N' -> (0x80|Z, N)"""
    if "#" in w:
        z, n = w.split("#")
        return 0x80 | int(z), int(n)
    return int(w), 0


def own_to_scs(msg):
    """Return the SCS wire frames bt_termo emits for an OWN message ([] if none)."""
    m = msg.strip()
    f = m.strip("*#").split("*")
    out = []
    if m.startswith("*4*"):                         # command *4*WHAT*WHERE##
        what, where = f[1], f[2]
        if not what.isdigit() and not (what.startswith("4002#") and "#" in where):
            pass
        elif what.startswith("4002#") and "#" in where:
            z, n = where.split("#")
            out.append([0x9E, 0x80 | int(z), 0x30 | int(n), int(what[5:])])
        elif where == "#0" and int(what) in CENTRAL:
            out.append([0xD1, 0x00, 0x03, 0x02, 0xC1, CENTRAL[int(what)], 0, 0])
        elif where.startswith("#") and int(what) in CENTRAL:     # zone group #N
            out.append([0xD1, 0x00, 0x03, 0x02, 0xC2, int(where[1:]), CENTRAL[int(what)], 0])
        elif "#" in where and int(what) != 1:
            pass
        elif "#" in where and int(what) == 1:
            z, _ = _zone(where)
            out.append([0xD1, z, 0x13, 0x02, 0xC1, 0xF0, 0, 0])
        elif int(what) in WHAT93 and where.isdigit() and int(where) < 100:
            out.append([0x93, int(where), 0x30, WHAT93[int(what)]])
        elif int(what) in WHAT9F and where.isdigit():
            out.append([0x9F, int(where), 0x30, WHAT9F[int(what)]])
    elif m.startswith("*#4*"):
        where = f[1]
        rest = f[2:]
        if not rest:                                # status request *#4*W##
            if where == "#0":
                out.append([0x99, 0x00, 0x30, 0xC0])
            elif where.startswith("#"):
                out.append([0xD1, 0x00, 0x03, 0x03, 0xC2, int(where[1:]), 0, 0])
            elif where.isdigit() and where != "0" and int(where) < 100:
                z = int(where)
                out += [[0x99, z, 0x30, x] for x in (0x00, 0x12, 0x0E, 0x0D)]
        elif rest[0].startswith("#"):               # write *#4*W*#DIM*...##
            dim = rest[0][1:]
            if where == "#0" and dim == "14":
                t, mo = int(rest[1]), int(rest[2])
                out.append([0xD1, 0x00, 0x03, 0x02, 0xC1, M14C[mo], t // 5, 0])
            elif dim == "14":
                out.append([0x8F + int(rest[2]), int(where), 0x30, int(rest[1]) // 5])
            elif dim == "11":
                out.append([0xD1, int(where), 0x03, 0x02, 0x0B, int(rest[1]), 0, 0])
            elif dim in ("5", "4"):
                out.append([0xD1, int(where), 0x03, 0x02, 0x02 if dim == "5" else 0x01,
                            int(rest[1]), 0, 0])
            elif dim == "7":
                out.append([0xD1, int(where), 0x03, 0x02, 0x05, 0xF0, int(rest[3]) // 5, 0])
            elif dim.startswith("8#"):
                out.append([0xD1, int(where), 0x03, 0x02, 0x04, int(dim[2:]) - 1,
                            int(rest[1]) // 5, 0])
            elif dim == "20":
                out.append([0xA6, int(where), 0x30, 0x00])
            elif dim == "31":
                out.append([0xD1, int(where), 0x03, 0x02, 0xC4, int(rest[1]), int(rest[2]), 0])
        else:                                       # dimension request *#4*W*DIM##
            dim = int(rest[0])
            if where.startswith("#"):
                if dim == 0:
                    out.append([0x99, 0x00, 0x30, 0x00])
            elif "#" in where:
                z, n = _zone(where)
                if dim == 20:
                    out.append([0x99, z, 0x30 | n, 0x10])
            elif where == "#0" and dim == 0:
                out.append([0x99, 0x00, 0x30, 0x00])
            elif where.isdigit() and len(where) == 3 and dim == 0:
                out.append([0x99, int(where[1:]), 0x30 | int(where[0]), 0x00])
            elif where.isdigit() and where != "0":
                z = int(where)
                if dim in REQ99:
                    out.append([0x99, z, 0x30, REQ99[dim]])
                elif dim in REQD1:
                    out.append([0xD1, z, 0x03, 0x03, REQD1[dim], 0, 0, 0])
                elif dim == 20:
                    out.append([0xA9, z, 0x30, 0x10])
    return [wire(bytes(x)) for x in out]


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("hex", "own"):
        print(__doc__)
        sys.exit(1)
    for a in sys.argv[2:]:
        r = scs_to_own(a) if sys.argv[1] == "hex" else own_to_scs(a)
        print("%-40s -> %s" % (a, " + ".join(r) if r else "(no translation)"))
