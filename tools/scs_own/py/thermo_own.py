"""WHO 4 OWN -> SCS, generalised from bt_termo sweeps (dim4_termo, ext4, ext4b, dl4, dl4b, dl4c).

Address model (bt_termo parses WHERE by splitting on '#'):
  zone      '1'..'99', zero-padded '01'      -> addr z,      hdr 03,      short 30, D1
  zone 0    '0'                              -> addr 00, D2 extended frames (broadcast); '00'/'000' -> D1
  central   '#0' / '#0#N'                    -> addr 00 / N, D1 (N behaves like a zone address)
  group     '#N'                             -> addr 00, D1; N only appears in the C2 group forms
  probe     'NZZ' (N 1..9)                   -> addr ZZ,     hdr N<<4|3, short 30|N, D1
  actuator  'Z#N' (Z 0..127, N 1..15)        -> addr 80|Z,   hdr N<<4|3, short 30|N, D1;  'Z#0' -> D5 Z 03
  interface 'X#4#NN' (any 'a#b#c...')        -> WHERE 'a' with a reduced dimension set; dim 22 -> zone b actuator c
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scs_own_fw import STAT, WHAT93, WHAT9F, M14C
INV_STAT = {v: k for k, v in STAT.items()}                # OWN status value -> SCS status byte (dim 20 writes)

REQ99 = {0: 0x00, 2: 0x0C, 3: 0x0F, 11: 0x0B, 12: 0x12, 13: 0x0D, 14: 0x0E, 16: 0x90, 17: 0x14, 19: 0x13,
         20: 0x10, 27: 0xF1, 28: 0xF2, 30: 0xC3, 31: 0xC4, 32: 0xC5}
REQD1 = {15: 0x21, 18: 0xCD, 21: 0x17, 29: 0x19, 60: 0x08}
REQD1_ZONE = {4: 0x01, 5: 0x02, 6: 0x03, 7: 0x05}                # extended requests only real zones answer
COMMON99 = (2, 3, 14, 30, 31, 32)                     # 99-type requests every address kind accepts
ZONE_ONLY99 = (11, 12, 13, 19, 27, 28)                # only real zones
STATE_DIMS = ('0', '12', '13', '15', '19', '20')     # *#4*W*DIM*values## is taken as the request of DIM
WR1 = {4: 0x01, 5: 0x02, 11: 0x0B}
# dimension 7: (mode*program) -> byte; None marks the two pairs that need a 4-digit temperature (byte 2 = T/5)
ENC7 = {'0*0': 0x00, '3*5': 0x00, '1*5': 0x00, '2*5': 0x00, '3*31': 0x00, '2*31': 0x00, '2*32': 0x00, '3*32': 0x00,
        '1*0': 0xF0, '2*0': 0xF1, '1*2': 0xF2, '2*2': 0xF3, '0*2': 0xF4, '1*31': 0xF9, '1*32': 0xFA, '0*5': 0xFF,
        '1*3': 0x10, '1*4': 0x11, '2*3': 0x12, '2*4': 0x13, '3*3': 0x14, '3*4': 0x15, '3*2': 0x16, '0*32': 0x16,
        '3*0': 0x17, '0*3': 0x18, '0*4': 0x19}
ENC7_TEMP = {'1*1': 0xF0, '0*1': 0x1A, '2*1': 0xF1, '3*1': 0x17}   # these need a temperature: byte 2 = T/5, 6..80
# temperatures are checked as T/5 (units of 0.5 C): (min, max) of T//5      [dl4b/dl4c/dl4d]
T7 = (6, 80)                                          # #7 with a temperature pair
T14 = (6, 80)                                         # #14 setpoint
T8 = {1: (28, 80), 2: (6, 69), 3: (20, 40), 4: (50, 70), 5: (6, 79), 6: (6, 79), 7: (20, 80), 8: (9, 80)}  # #8#N (1: 0100 rejected, 0140 accepted)
V0_MAX = 511                                          # #0 (16-bit) upper bound
V3_MIN, V3_MAX = 30, 200                              # #3 range (25 and 201 rejected)
L21 = (3, 3, 100)                                     # #21 max a, b, c
L29 = (100, 3, 100)                                   # #29 max a, b, c
L18 = (9, 255)                                        # #18 max a, b (10 rejected, 255 accepted)
CEN_CODE = {0: (0xF1, 0), 1: (0xF0, 0), 102: (0x17, 0), 103: (0x16, 0), 115: (0x14, 0), 202: (0x27, 0),
            203: (0x26, 0), 215: (0x24, 0), 302: (0x07, 0), 303: (0x06, 0), 315: (0x04, 0), 3000: (0x05, 0),
            1100: (0x11, 0), 1200: (0x13, 0), 2100: (0x21, 0), 2200: (0x23, 0)}
GRP_MODE = {102: 0x17, 103: 0x16, 202: 0x27, 203: 0x26, 302: 0x07, 303: 0x06}
GRP_CODE = {111: 0x10, 211: 0x20, 311: 0x00}


def central_code(what):
    """WHAT of a central-unit command -> (code, b2) or None"""
    if what in CEN_CODE:
        return CEN_CODE[what]
    if 1101 <= what <= 1199: return 0x11, what - 1101
    if 1201 <= what <= 1299: return 0x13, what - 1201
    if 2101 <= what <= 2199: return 0x21, what - 2101
    if 2201 <= what <= 2299: return 0x23, what - 2201
    if 3100 <= what <= 3199: return 0x01, (what - 3101) & 0xFF
    if 3200 <= what <= 3299: return 0x03, (what - 3201) & 0xFF
    return None


class Addr:
    __slots__ = ('kind', 'addr', 'hdr', 'short', 'pfx', 'n', 'iface', 'parts', 'pad')

    def __init__(self, kind, addr, hdr=0x03, short=0x30, pfx=0xD1, n=0, iface=False, parts=(), pad=False):
        self.kind, self.addr, self.hdr, self.short, self.pfx, self.n, self.iface, self.parts, self.pad = kind, addr, hdr, short, pfx, n, iface, parts, pad

    def ext(self, t, *body):
        """extended frame  pfx addr hdr t b0 b1 b2 b3"""
        return [self.pfx, self.addr, self.hdr, t] + list(body) + [0] * (4 - len(body))

    def sh(self, c, v):
        return [c, self.addr, self.short, v]


def parse_where(w):
    parts = w.split('#')
    iface = False
    if len(parts) >= 3 and parts[0] != '':                 # 'X#4#NN' and any other 3+ part form: bt_termo keeps 'X'
        iface = True
        w = parts[0]
    elif len(parts) == 2 and parts[0] != '':               # actuator Z#N
        z, n = parts
        if not (z.isdigit() and n.isdigit()) or int(z) > 127 or int(n) > 15:
            return None
        if int(n) == 0:
            return Addr('actuator0', int(z), pfx=0xD5, n=0, parts=parts)
        return Addr('actuator', 0x80 | int(z), (int(n) << 4) | 3, 0x30 | int(n), n=int(n), parts=parts)
    elif parts[0] == '':                                   # '#0', '#0#N', '#N' (with optional interface suffix)
        p = parts[1:]
        if len(p) >= 3:                                    # '#0#2#4#01', '#1#4#01': everything after the first part is dropped
            iface = True; p = p[:1]
        if not all(x.isdigit() for x in p) or len(p) > 2:
            return None
        if p[0] == '0':
            n = int(p[1]) if len(p) == 2 else 0
            if n > 255: return None
            return Addr('central' if n == 0 else 'centralN', n, iface=iface, parts=parts)
        if len(p) != 1 or int(p[0]) > 255:
            return None
        return Addr('group', 0, n=int(p[0]), iface=iface, parts=parts)
    if not w.isdigit() or len(w) > 3:
        return None
    if len(w) == 3:                                        # probe NZZ
        n, zz = int(w[0]), int(w[1:])
        if n == 0:
            w = w[1:]                                      # '0ZZ' is zone ZZ (zero padded)
        else:
            return Addr('probe', zz, (n << 4) | 3, 0x30 | n, n=n, iface=iface, parts=parts)
    z = int(w); pad = len(w) > 1 and w[0] == '0'
    if z == 0:
        return Addr('zone0', 0, pfx=0xD1 if (iface or pad) else 0xD2, iface=iface, parts=parts, pad=pad)
    if z > 99:
        return None
    return Addr('zone', z, iface=iface, parts=parts, pad=pad)


def _v20(v0):
    if v0 < 100: return INV_STAT.get(v0)                 # 0..22 known status values, 23..99 rejected
    return (0x80 + v0 - 100) & 0xFF                       # 100.. wraps modulo 256 (228 -> 00, 355 -> 7F)


def own_to_scs(msg):
    m = msg.strip()
    f = m.strip('*#').split('*')
    out = []
    if m.startswith('*4*'):
        what, where = f[1], f[2]
        A = parse_where(where)
        if A is None or A.kind == 'actuator0' and what not in ('0', '1'):
            return []
        k = A.kind
        if what[:4] in ('4001', '4002') and (len(what) == 4 or what[4] == '#'):      # *4*4001[#V]*W##
            c = 0x9D if what[:4] == '4001' else 0x9E
            v = int(what[5:]) if '#' in what else 0
            if k in ('zone', 'zone0', 'probe', 'central', 'centralN', 'group') and v == 0:
                return [A.sh(c, 0)]
            if k == 'actuator' and (v == 0 or (A.addr & 0x7F) == 0) and v < 256:
                return [A.sh(c, v)]
            return []
        base, sub = (what.split('#') + [None])[:2]
        if not base.isdigit():
            return []
        w = int(base)
        if w in (0, 1) and sub is None:                    # generic on/off: zones use the short 93 form, all others the central form
            if k == 'zone' and not A.iface:
                return [A.sh(0x93, 0x01 if w == 0 else 0x00)]
            if k == 'actuator0':
                return [[0xD5, A.addr, 0x03, 0x02, 0xC1, 0xF1 if w == 0 else 0xF0, 0, 0]]
            return [A.ext(0x02, 0xC1, 0xF1 if w == 0 else 0xF0)]
        if k in ('central', 'centralN'):
            cc = central_code(w)
            if w == 115 and sub and sub.isdigit() and 1101 <= int(sub) <= 1199:
                cc = (0x14, int(sub) - 1101)
            elif sub is not None:
                cc = None
            if cc:
                out.append(A.ext(0x02, 0xC1, cc[0], cc[1]))
            elif w in GRP_CODE:
                out.append(A.ext(0x02, 0xC2, 0x00, GRP_CODE[w]))
        elif k == 'group' and sub is None:
            if w in GRP_MODE:
                out.append(A.ext(0x02, 0xC2, A.n, GRP_MODE[w]))
            elif w in GRP_CODE:
                out.append(A.ext(0x02, 0xC2, A.n, GRP_CODE[w]))
        elif k == 'zone' and sub is None and not A.iface:
            if w == 39:
                out.append(A.sh(0x93, 0x0D))
            elif w == 45:
                out.append(A.ext(0x02, 0xF0, 0xFF, 0xFF))
            elif w in WHAT93:
                out.append(A.sh(0x93, WHAT93[w]))
            elif w in WHAT9F:
                out.append(A.sh(0x9F, WHAT9F[w]))
        return out
    if not m.startswith('*#4*'):
        return []
    where, rest = f[1], f[2:]
    A = parse_where(where)
    if A is None or A.kind == 'actuator0':
        return []
    k = A.kind
    zone_like = k in ('zone', 'probe', 'actuator')
    if rest and not rest[0].startswith('#') and len(rest) > 1:                 # state form -> request
        if rest[0] not in STATE_DIMS:
            return []
        rest = rest[:1]
    if not rest:                                                             # *#4*W##
        if k in ('central', 'centralN'):
            return [A.sh(0x99, 0xC0)]
        if k == 'group':
            return [A.ext(0x03, 0xC2, A.n)]
        if k == 'zone' and not A.iface:
            return [A.sh(0x99, x) for x in (0x00, 0x12, 0x0E, 0x0D)]
        return []
    if not rest[0].startswith('#'):                                          # ---------------- request
        if not rest[0].isdigit():
            return []
        dim = int(rest[0])
        if dim == 22:                                                        # only the 3-part 'a#b#c' form: zone b, actuator c
            p = A.parts
            if A.iface and len(p) == 3 and all(x.isdigit() for x in p) and 0 < int(p[1]) < 128 and 0 < int(p[2]) < 16:
                return [[0xD1, 0x80 | int(p[1]), (int(p[2]) << 4) | 3, 0x03, 0x16, 0, 0, 0]]
            return []
        if dim in COMMON99:
            return [A.sh(0x99, REQ99[dim])]
        if A.iface and (dim == 0 or dim in ZONE_ONLY99 or dim in REQD1_ZONE):
            return []
        if dim == 0:
            if k == 'zone0' or (k == 'zone' and A.pad):                      # '0', '00', '01': one request per probe 1..8
                return [[0x99, A.addr, 0x31 + i, 0x00] for i in range(8)]
            if k in ('zone', 'central', 'group', 'probe'):
                return [A.sh(0x99, 0x00)]
            return []
        if dim in ZONE_ONLY99:
            return [A.sh(0x99, REQ99[dim])] if k == 'zone' else []
        if dim == 16:
            return [A.sh(0x99, 0x90)] if k in ('probe', 'actuator') else []
        if dim == 17:
            return [A.sh(0x99, 0x14)] if k == 'actuator' and A.addr & 0x7F else []
        if dim == 20:
            if k in ('zone', 'centralN'): return [A.sh(0xA9, 0x10)]
            if k in ('zone0', 'central', 'group'): return [A.sh(0xB9, 0x10)]
            if k == 'actuator': return [A.sh(0x99, 0x10)]
            return []
        if dim == 15:
            return [A.ext(0x03, 0x21)] if zone_like or k == 'zone0' else []
        if dim in (21, 29) and (k == 'probe' or (k == 'actuator' and not A.addr & 0x7F)):   # probes never, actuators of zone 0 never
            return []
        if dim in REQD1:
            return [A.ext(0x03, REQD1[dim])]
        if dim in REQD1_ZONE and k == 'zone':
            return [A.ext(0x03, REQD1_ZONE[dim])]
        return []
    # ------------------------------------------------------------------------- write  *#4*W*#DIM*values##
    dspec = rest[0][1:]; a = rest[1:]; na = len(a)
    if not all(x.isdigit() for x in a) or not na:
        return []
    ai = [int(x) for x in a]
    if dspec.startswith('8#'):
        if k != 'zone' or A.iface or na != 1 or not dspec[2:].isdigit() or int(dspec[2:]) not in T8:
            return []
        lo, hi = T8[int(dspec[2:])]
        if len(a[0]) < 2 or len(a[0]) > 4 or not lo <= ai[0] // 5 <= hi:
            return []
        return [A.ext(0x02, 0x04, int(dspec[2:]) - 1, ai[0] // 5)]
    if dspec.startswith('14#'):
        dspec = '14'
    if not dspec.isdigit():
        return []
    dim = int(dspec)
    if dim == 20 and (na == 1 or (na == 2 and a[1] == '0')):
        v = _v20(ai[0])
        if v is None or k in ('group',) and False:
            return []
        c = {'zone': 0xA6, 'centralN': 0xA6, 'probe': 0x96, 'actuator': 0x96}.get(k, 0xB6)
        return [A.sh(c, v)]
    if dim in (21, 29) and na == 3:
        lim = L21 if dim == 21 else L29
        if all(ai[i] <= lim[i] for i in range(3)):
            return [A.ext(0x02, 0x17 if dim == 21 else 0x19, *ai)]
        return []
    if dim in (31, 32) and na >= 2:
        if ai[0] <= (23 if dim == 31 else 24) and ai[1] <= 59:
            return [A.ext(0x02, 0xC4 if dim == 31 else 0xC5, ai[0], ai[1])]
        return []
    if dim == 18 and na == 2:
        if ai[0] <= L18[0] and ai[1] <= L18[1]:
            return [A.ext(0x02, 0xCD, ai[0], ai[1])]
        return []
    if dim == 17 and na == 3:
        if k in ('probe', 'actuator') and not A.iface and max(ai[:2]) <= 255 and ai[2] < 1280:
            return [A.ext(0x02, 0x14, ai[0], ai[1], ai[2] // 5)]
        return []
    if dim == 14 and na == 2:
        t, mo = ai
        if A.iface:
            return []
        if not T14[0] <= t // 5 <= T14[1]:
            return []
        if k in ('central', 'centralN') and mo in M14C and len(a[0]) == 4:
            return [A.ext(0x02, 0xC1, M14C[mo], t // 5)]
        if k == 'group' and mo in M14C and len(a[0]) == 4:
            return [A.ext(0x02, 0xC2, A.n, M14C[mo], t // 5)]
        if k == 'zone' and 1 <= mo <= 3:
            return [A.sh(0x8F + mo, t // 5)]
        return []
    if k != 'zone' or A.iface:                                               # the remaining dimensions are zone-only
        return []
    if dim == 0 and na == 1 and ai[0] <= V0_MAX:
        return [A.ext(0x02, 0xF0, ai[0] >> 8, ai[0] & 0xFF)]
    if dim == 3 and na == 1 and V3_MIN <= ai[0] <= V3_MAX:
        return [A.ext(0x02, 0x0F, ai[0] >> 8, ai[0] & 0xFF)]
    if dim in WR1 and na == 1 and ai[0] <= 3:
        return [A.ext(0x02, WR1[dim], ai[0])]
    if dim == 7 and na in (2, 3):
        pair = '%d*%d' % (ai[0], ai[1])
        if pair in ENC7_TEMP:
            if na == 3 and T7[0] <= ai[2] // 5 <= T7[1]:
                return [A.ext(0x02, 0x05, ENC7_TEMP[pair], ai[2] // 5)]
            return []
        if pair in ENC7:
            code = ENC7[pair]
            b2 = 0x00 if code == 0x00 else 0xFF              # code 00: bt_termo emits 00 or 0C non-deterministically
            return [A.ext(0x02, 0x05, code, b2)]
    return []
