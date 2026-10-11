#!/usr/bin/env python3
"""Standalone SCS <-> OpenWebNet translator for BTicino MyHOME (mhs1 firmware behaviour).

Covers WHO 1 lighting (incl. dimmers, all dimensions), WHO 2 automation/covers, WHO 4
thermoregulation (all dimensions), WHO 9 auxiliaries, WHO 18 energy, plus the WHO 0/14
frames bt_luci emits. Every rule and table was recovered by running the firmware's own
translators (bt_luci, coso, bt_termo, bt_supervisione) on an emulated bus; see
SCS_OWN_ALL_MAP.md. Needs fw_tables.json next to this file.

    python3 scs_own_all.py hex "A8 B8 31 12 00 9B A3" "A8 D2 28 03 34 12 F0 00 C8 E7 A3"
    python3 scs_own_all.py own "*1*1*31##" "*2*1*31##" "*#4*40*14##" "*#18*51*113##"

    from scs_own_all import scs_to_own, own_to_scs
"""
import json, os, re, sys
from gw_inverse import gateway_own

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scs_own_fw as thermo          # WHO 4 SCS->OWN (validated 29,693/29,693)
import thermo_own                    # WHO 4 OWN->SCS (all dimensions)
import energy_own                    # WHO 18 OWN->SCS
import cen_own                       # WHO 15 / 25 OWN->SCS
import device_own                    # WHO 1004 / 1013 OWN->SCS (bt_device)
import sound_own                     # WHO 22 OWN->SCS (bt_multi)

_T = json.load(open(os.path.join(HERE, 'fw_tables.json')))
S_STATUS = {int(k): v for k, v in _T['S_STATUS'].items()}
S_POINT = {int(k): v for k, v in _T['S_POINT'].items()}
S_GENERAL = {int(k): v for k, v in _T['S_GENERAL'].items()}
S_AREA = {int(k): v for k, v in _T['S_AREA'].items()}
S_GROUP = {int(k): v for k, v in _T['S_GROUP'].items()}
S_OTHER, AUX, EXT, ENERGY, O2S = (_T[k] for k in ('S_OTHER', 'AUX', 'EXT', 'ENERGY', 'O2S'))
CEN = _T.get('CEN', {})
MISC = _T.get('MISC', {})                 # bt_device / bt_multi frames, exact keys

# WHAT -> command value byte for WHO 1 (from *1*WHAT*31## sweep)
WHAT2VAL = {0: 0x01, 1: 0x00, 20: 0x0B, 30: 0x03, 31: 0x04}
WHAT2VAL.update({n: ((n - 1) << 4) | 0x0D for n in range(2, 11)})      # dimmer 20..100 %
WHAT2VAL.update({n: ((n - 10) << 4) | 0x06 for n in range(11, 19)})    # timers 1 min .. 
WHAT2VAL.update({n: ((n - 20) << 4) | 0x0B for n in range(21, 30)})    # timers
for k, v in O2S.items():                                               # anything else observed
    m = re.match(r'\*1\*(\d+)\*31##$', k)
    if m and v and len(v[0]) == 8:
        WHAT2VAL.setdefault(int(m.group(1)), int(v[0][6:8], 16))


# ---------------------------------------------------------------- helpers
def xor(bs):
    x = 0
    for b in bs:
        x ^= b
    return x


def wire(body):
    return "A8 " + " ".join("%02X" % b for b in body) + " %02X A3" % xor(body)


def parse_hex(s):
    b = bytes.fromhex(re.sub(r"[^0-9A-Fa-f]", "", s))
    if len(b) >= 3 and b[0] in (0xA8, 0xB8, 0xD4) and b[-1] == 0xA3:
        b = b[1:-2]
    elif len(b) in (5, 9) and xor(b[:-1]) == b[-1]:
        b = b[:-1]
    return b


def where_from_addr(a):
    """light/cover address byte -> WHERE: '%X%X' if both nibbles < 10 else '%02d%02d'"""
    A, PL = a >> 4, a & 0x0F
    return "%d%d" % (A, PL) if A < 10 and PL < 10 else "%02d%02d" % (A, PL)


def addr_from_where(w):
    if not w.isdigit():
        return None
    if len(w) == 2:
        return int(w[0]) << 4 | int(w[1])
    if len(w) == 4 and int(w[:2]) < 16 and int(w[2:]) < 16 and (int(w[:2]) >= 10 or int(w[2:]) >= 10):
        a = int(w[:2]) << 4 | int(w[2:])
        return a if a != 0xFF else None
    return None


def _sub_where(msgs, old, new):
    return [re.sub(r'\*%s(#|\*|##)' % re.escape(old), lambda m: '*' + new + m.group(1), x) for x in msgs]


# ---------------------------------------------------------------- SCS -> OWN
def scs_to_own(frame, gateway=True):
    """frame: 'A8 .. A3' string, body hex, or bytes. Returns list of OWN messages."""
    b = parse_hex(frame) if isinstance(frame, str) else bytes(frame)
    out = list(thermo.scs_to_own(b))
    out += MISC.get(b.hex().upper(), [])
    if len(b) == 4:
        out += _short(*b)
    elif len(b) == 8:
        out += _ext(b)
    if not out and gateway:                                  # not a bus event: maybe a request the gateway itself sent
        out = gateway_own(b)
    return list(dict.fromkeys(out))


def _short(c, a, s, v):
    out = []
    if s == 0x12:                                            # lights / covers
        if c == 0xB8:
            out += ["*%s*%s*%s##" % (who, what, where_from_addr(a)) for who, what in S_STATUS.get(v, [])]
        elif c == 0xB1:                                      # general command (byte 2 is ignored by bt_luci)
            out += ["*%s*%s*0##" % (who, what) for who, what in S_GENERAL.get(v, [])]
        elif c == 0xB3:
            out += ["*%s*%s*%s##" % (who, what, '00' if a == 0 else '%d' % a) for who, what in S_AREA.get(v, [])]   # area 0 is written '00'
        elif c == 0xB5:
            out += ["*%s*%s*#%d##" % (who, what, a) for who, what in S_GROUP.get(v, [])]
        elif c in (0xB2, 0xB4, 0xCD):                        # bt_luci quirks: B2 -> point 00, B4 -> point 0153 (0x99), CD -> point a
            w = {0xB2: '00', 0xB4: '0153', 0xCD: where_from_addr(a)}[c]
            out += ["*%s*%s*%s##" % (who, what, w) for who, what in S_POINT.get(v, [])]
        elif c < 0xB0 or c > 0xB8:                           # point command, a = source
            out += ["*%s*%s*%s##" % (who, what, where_from_addr(c)) for who, what in S_POINT.get(v, [])]
    elif c in (0xCD, 0xB2, 0xB1, 0xB4, 0xB3, 0xB5) and (s >> 4 == 0x9 or s in (0x10, 0x11, 0x14, 0x15, 0x04)):
        out += _cen_frame(c, a, s, v)
    if s >> 4 == 0x9 and c in (0xB0, 0xB1, 0xB3, 0xB5, 0xB8):   # WHO 9 aux (coso) - the same frame may also be a CEN event for bt_luci
        # coso only looks at bytes 3-4 (9A|9B|9C, WHERE<<4|code); byte 1 must be B0/B1/B3/B5/B8, byte 2 is ignored
        out += AUX.get("B831%02X%02X" % (s, v), [])
    if s == 0x12 or s >> 4 == 0x9 or (c in (0xCD, 0xB2, 0xB1, 0xB4, 0xB3, 0xB5) and s in (0x10, 0x11, 0x14, 0x15, 0x04)):
        pass
    else:
        k = ("B8_" if c == 0xB8 else "31_") + "%02X%02X" % (s, v)
        w = where_from_addr(a if c == 0xB8 else c)
        if k in S_OTHER:
            out += _sub_where(S_OTHER[k], '31', w)
        elif c == 0xB8 and s == 0x17 and v >> 6 != 2:         # WHO 0 scenario event (0x80..0xBF are dropped)
            out += ["*0*%d*%s##" % (v, w)]
        elif c == 0xB8 and s == 0x1C:                        # WHO 0 scenario status: bits 7-5 select WHAT, bits 4-0 the scenario
            hi, n = v >> 5, v & 0x1F
            sfx = '#%d' % n if n else ''
            if v == 0xFF: out += ["*0*43*%s##" % w]
            elif hi == 0: out += ["*0*42*%s##" % w]
            elif hi == 1: out += ["*0*42%s*%s##" % (sfx, w)]
            elif hi == 2: out += ["*0*40%s*%s##" % (sfx, w)]
            elif hi == 3: out += ["*0*41%s*%s##" % (sfx, w)]
            elif hi == 4: out += ["*0*%d*%s##" % (41 if n == 0 else 40, w), "*0*44*%s##" % w]
            elif hi == 5: out += ["*0*46%s*%s##" % (sfx, w)]
            elif hi == 6: out += ["*0*45*%s##" % w]
    return out


def _cen_frame(c, a, s, v):
    """CEN / CEN+ frames from bt_luci: exact table first, then the recorded address generalised"""
    key = "%02X%02X%02X%02X" % (c, a, s, v)
    if key in CEN:
        return CEN[key]
    if c == 0xCD:                                              # CEN, WHO 15
        w = where_from_addr(a)
        if s == 0x14:
            return ["*15*%02d*%s##" % (v, w)]
        if s == 0x10:
            return ["*15*%02d#%d*%s##" % (v & 0x1F, v >> 5, w)]
        if s == 0x11:
            return ["*15*%02d#%d*%s##" % (v & 0x1F, (v >> 5) + 3, w)]
        return []
    if c == 0xB2 and 0x90 <= s <= 0x97:                        # CEN+ button events, WHERE 2<0..2047>
        return ["*25*%d#%d*2%d##" % (21 + s - 0x90, v & 0x1F, a | ((v >> 5) << 8))]
    if c == 0xB1 and s in (0x93, 0x94, 0x95, 0x96, 0x97):     # CEN+ zone 1
        return [{0x93: "*25*11#%d*1%d##" % (v, a), 0x94: "*25*12*1%d##" % a, 0x95: "*25*13#%d#1*1%d##" % (v, a),
                 0x96: "*25*14#%d#1*1%d##" % (v, a), 0x97: "*25*15*1%d##" % a}[s]]
    if c == 0xB4 and s == 0x90:                                # CEN+ zone 3: BCD below 0x9A (printed %X), else value - 54 (0x9A = 100)
        return ["*#25*3%s##" % ('%X' % v if v < 0x9A else '%d' % (v - 54))]
    if c == 0xB4 and s in (0x91, 0x92) and v <= 1:
        return ["*25*%d#%d*3%X##" % (31 + v, s - 0x91, a)]
    if s == 0x10 and v == 0 and c in (0xB1, 0xB3, 0xB5):
        return ["*14*1*%s##" % ('0' if c == 0xB1 else ('%d' if c == 0xB3 else '#%d') % a)]
    return []


def _ext(b):
    key = b.hex().upper()
    if key in EXT:
        return EXT[key]
    if key in ENERGY:
        return ENERGY[key]
    # generalise the recorded light/cover extended frames over the address byte
    if b[0] in (0xD1, 0xD2, 0xD5) and b[2] in (0x01, 0x11) and b[3] in (0x42, 0x43, 0x44, 0x32, 0x34):
        k31 = key[:2] + '31' + key[4:]
        if k31 in EXT:
            return _sub_where(EXT[k31], '31', where_from_addr(b[1]))
    if b[0] in (0xD1, 0xD2) and b[2] & 0x0F == 1 and b[4] == 0x0D and b[3] in (0x34, 0x44, 0x32) and b[5] in (0x0D, 0x01, 0x00, 0x10):
        return _dimmer_status(b)
    if b[0] == 0xD2 and b[2] == 0x09 and b[3] & 0x0F in (6, 7):                                    # WHO 13 clock broadcast (bt_device)
        return _clock_frame(b)
    if b[0] in (0xD1, 0xD2, 0xD5) and b[3] in (0x32, 0x34, 0x42, 0x44) and b[4] in LDIM:
        return _light_dim_frame(b)
    if b[0] in (0xD1, 0xD2, 0xD5) and b[3] in (0x32, 0x42, 0x44) and b[4] == 0x09 and b[2] & 0x0F == 1:
        return _cover_adv_frame(b)
    if b[0] == 0xD2 and b[2] == 0x02 and b[3] >> 4 == 3:  # energy answers, meter address 0xA0|N
        kA1 = key[:2] + 'A1' + key[4:]
        if kA1 in ENERGY and b[1] >> 4 == 0xA:
            return _sub_where(ENERGY[kA1], '51', '5%d' % (b[1] & 0x0F))
    return []


def _dimmer_status(b):
    """bt_luci dimmer level frames  D1|D2 aa bb 34|44 0D x lv sp:  x=0D -> dim 1, level 100+lv;  x=01 -> dim 4, level 100;
       x=00 (D1 only) / x=10 -> dim 4, level 100+lv;  lv=sp=0 -> *1*0*W##;  cmd 32 with x=01 -> *1*1000#0#4*W##"""
    aa, bb, cmd, x, lv, sp = b[1], b[2], b[3], b[5], b[6], b[7]
    w = where_from_addr(aa) + ('#4#%02d' % (bb >> 4) if bb >> 4 else '')
    if cmd == 0x32:
        return ["*1*1000#0#4*%s##" % w] if x == 0x01 else []
    if x == 0x00 and b[0] != 0xD1:
        return []
    if lv == 0 and sp == 0:
        return ["*1*0*%s##" % w]
    dim = 1 if x == 0x0D else 4
    return ["*#1*%s*%d*%d*%d##" % (w, dim, 100 if x == 0x01 else 100 + lv, sp)]


def _clock_frame(b):
    """bt_device clock broadcasts (D2 aa 09 x6 / x7). Bytes are read as text: the decimal prefix of the two hex
    digits ('22' -> 22, '2A' -> 2, 'AB' -> 0).
       D2 aa 09 x6 hh mm ss tz -> *#13**#0*hh*mm*ss*TZ##   TZ = '' when tz low nibble is F, else bit4 + low nibble
       D2 aa 09 x7 dd wm yy yy -> *#13**#1*W*DD*MM*YYYY##  W = wm high nibble (F -> 0), MM = wm low nibble"""
    def dec(x):
        s, v = '%02X' % x, 0
        for ch in s:
            if not ch.isdigit(): break
            v = v * 10 + int(ch)
        return v
    if b[3] & 0x0F == 6:
        tz = b[7]
        tzs = '' if tz & 0x0F == 0x0F else '%d%02d' % ((tz >> 4) & 1, tz & 0x0F)
        return ["*#13**#0*%02d*%02d*%02d*%s##" % (dec(b[4]), dec(b[5]), dec(b[6]), tzs)]
    dd, wm = b[4], b[5]
    # note: bt_device itself drops frames with dd == 0x28 (firmware quirk); the translator still decodes them
    day = dec(dd) if dec(dd) < 40 else 0
    w = wm >> 4 if wm >> 4 != 0xF else 0
    return ["*#13**#1*%02d*%02d*%02d*%02d%02d##" % (w, day, wm & 0x0F, dec(b[6]), dec(b[7]))]


LDIM = {0x06: 2, 0x0C: 12, 0x10: 6, 0x15: 5, 0x16: 7, 0x17: 8}      # dimension code byte -> WHO 1 dimension


def _light_dim_frame(b):
    """bt_luci decoding of any D1/D2/D5 .. 32|34|42|44 <dim> v1 v2 v3 frame (write *#1*W*#D*.., status *#1*W*D*..)"""
    aa, bb, cmd, dim = b[1], b[2], b[3], LDIM[b[4]]
    i = bb >> 4
    status = cmd & 0x0F == 4
    ifs = lambda i: '#4#%02d' % i if i else ''
    if status and dim == 5 or bb & 0x0F != 1 or (b[0] == 0xD5 and i > 2):   # dim 5 has no status form; header byte must be x1 (D5: 01/11/21)
        return []
    if b[0] == 0xD1:
        w = where_from_addr(aa) + ifs(i)
    elif b[0] == 0xD2:
        w = ('00' + ifs(i) if i else '0') if aa == 0 else where_from_addr(aa) + ifs(i)
    else:                                                     # D5: bb 01 -> group #aa ; 11 -> area ; 21 -> general
        if status and dim == 12:
            return []
        if bb == 0x01: w = '#%d' % aa
        elif i == 2:
            if cmd == 0x32 or aa & 0x0F or dim == 12:
                return []
            w = '0' + ifs(aa >> 4)
        elif cmd == 0x32: w = '%02d' % aa
        else: w = '%d' % (aa & 0x0F) + ifs(aa >> 4)
    if dim == 12:                                             # 9-bit first value in the status forms, byte 2 keeps 7 bits
        v0 = b[5] + (256 if status and b[6] & 0x80 else 0)
        val = '%d*%d*%d' % (v0, b[6] & 0x7F, b[7])
    elif dim in (2, 7):
        val = '%d*%d*%d' % (b[5], b[6], b[7])
    elif dim in (5, 6):
        val = '%d' % (((b[5] & 0x0F) << 16) | (b[6] << 8) | b[7])
    else:
        val = '%d' % ((b[5] << 16) | (b[6] << 8) | b[7])
    return ["*#1*%s*%s%d*%s##" % (w, '#' if cmd & 0x0F == 2 else '', dim, val)]


COVER_ADV = {0: '10', 1: '11', 2: '12', 3: '#11', 4: '14', 5: '13', 0xF: '#13'}   # byte 5 high nibble -> WHAT / dimension


def _cover_adv_frame(b):
    """coso decoding of the advanced cover frames  D1|D2|D5 aa bb 32|42|44 09 xx v y
    xx: high nibble = WHAT (10..14) or dimension (#11, #13), low nibble = bit3 -> Q, bits 2..0 -> PPP (binary string).
    Note: coso only emits these for devices it has learned from earlier bus traffic."""
    aa, bb, cmd, x = b[1], b[2], b[3], b[5]
    hi, q, ppp = x >> 4, (x >> 3) & 1, format(x & 7, '03b')
    what = COVER_ADV.get(hi)
    if what is None:
        return []
    i = bb >> 4
    ifs = '#4#%02d' % i if i else ''
    if b[0] == 0xD1:
        w = where_from_addr(aa) + ifs
    elif b[0] == 0xD2:                                        # general: 00 11 -> '0', 00 21 -> '0#4#01'
        w = ('0' + ('#4#%02d' % (i - 1) if i > 1 else '')) if aa == 0 else where_from_addr(aa) + ifs
    else:                                                     # D5 aa 01 -> group #aa ; aa 11 -> area (00 -> '00') ; aa 21 -> general with interface
        if bb == 0x01: w = '#%d' % aa
        elif i == 2: w = '0#4#%02d' % (aa >> 4)
        elif i == 1 and aa >> 4 == 0: w = '%02d' % aa if aa == 0 else '%d' % aa
        elif aa & 0x0F < 10: w = '#%d#4#%02d' % (aa & 0x0F, aa >> 4)        # D5 aa 11|31: group aa&F with interface aa>>4
        else: w = '#4#%02d' % (aa >> 4)                                       # group number >= 10 is dropped by coso
    if cmd == 0x44:                                           # status  *#2*W*10*<what>*v*PPP*<y hi>##  (only for the WHAT codes)
        return ["*#2*%s*10*%s*%d*%s*%d##" % (w, what, b[6], ppp, b[7] >> 4)] if not what.startswith('#') else []
    if what == '#11':
        return ["*#2*%s*#11#%s#%d*%d##" % (w, ppp, q, b[6])]
    if what == '#13':
        return ["*#2*%s*#13#%d*%s##" % (w, q, ppp)]
    if what in ('11', '12'):
        body = '%s#%d#%s#%d' % (what, b[6], ppp, q)
    else:
        body = '%s#%s#%d' % (what, ppp, q)
    return ["*2*%s%s*%s##" % ('1000#' if b[0] == 0xD1 else '', body, w)]


# ---------------------------------------------------------------- OWN -> SCS
def _light_addr(where):
    iface = None
    if '#4#' in where:
        mm = re.fullmatch(r'(#?[^#]*)#4#(\d{2})', where)
        if not mm:
            return None, None
        where, iface = mm.group(1), int(mm.group(2))
    if where == '0':
        return [0xB1, 0x00], iface
    if where == '00':
        return [0xB3, 0x00], iface
    if where == '100':
        return [0xB3, 0x0A], iface
    if where.startswith('#') and where[1:].isdigit():
        return [0xB5, int(where[1:])], iface
    if where.isdigit() and len(where) == 1:
        return [0xB3, int(where)], iface
    a = addr_from_where(where)
    return ([a, 0x00], iface) if a is not None else (None, None)


def _cover_ext_hdr(base, iface):
    """coso extended header: point D1 aa 01, area D5 0A 11, group D5 0N 01, general D2 00 01"""
    return _light_ext_hdr(base, iface)


def _light_ext_hdr(base, iface):
    if base[0] == 0xB1:
        hdr = [0xD2, 0x00, 0x01]
    elif base[0] == 0xB3:
        hdr = [0xD5, base[1], 0x11]
    elif base[0] == 0xB5:
        hdr = [0xD5, base[1], 0x01]
    else:
        hdr = [0xD1, base[0], 0x01]
    if iface is not None:
        if base[0] == 0xB1:                                  # general through an interface becomes D5 i0 (i+1)1
            hdr = [0xD5, iface << 4, ((iface + 1) << 4) | 0x01]
        elif base[0] == 0xB5:
            hdr = [0xD5, (iface << 4) | base[1], ((iface + 1) << 4) | 0x01]
        elif base[0] == 0xB3:
            hdr = [0xD5, (iface << 4) | base[1], (iface << 4) | 0x01]
        else:
            hdr[2] |= iface << 4
    return hdr


def _lights(msg):
    """WHO 1 / WHO 2 -> list of body byte-lists (from bt_luci / coso behaviour)"""
    m = msg.strip()
    f = m.strip('*#').split('*')
    out = []
    if len(f) < 3 and not (m.startswith('*#') and len(f) >= 2):
        return []
    if m.startswith('*14*') and f[1] in ('0', '1'):             # WHO 14 actuator lock (0) / unlock (1)
        base, iface = _light_addr(f[2])
        if base is None:
            return []
        body = base + [0x11 if f[1] == '0' else 0x10, 0x00]
        return [[0xEC, iface, 0x00, 0x00] + body if iface is not None else body]
    if m.startswith('*9*'):                                     # WHO 9 aux command (coso)
        what, where = f[1], f[2]
        if not (what.isdigit() and where.isdigit() and int(where) <= 15 and int(what) <= 10):
            return []
        t, code = {0: (0x9A, 0), 1: (0x9A, 4), 2: (0x9A, 8), 9: (0x9A, 0xC), 3: (0x9B, 0), 4: (0x9B, 4), 5: (0x9B, 8), 10: (0x9B, 0xC),
                   6: (0x9C, 1), 7: (0x9C, 2), 8: (0x9C, 4)}[int(what)]
        return [[0xB0, 0x00, t, (int(where) << 4) | code]]
    if m.startswith('*0*'):                                     # WHO 0 scenario command (bt_luci sends it twice)
        what, where = f[1], f[2]
        iface = None
        mm = re.fullmatch(r'(#?[^#]*)#4#(\d{2})', where)
        if mm:
            where, iface = mm.group(1), int(mm.group(2))
        if not what.isdigit() or (int(what) > 31 and what != '44'):
            return []
        if where == '0':
            a = 0x00
        elif re.fullmatch(r'#?\d', where):
            a = int(where.lstrip('#'))
        else:
            a = addr_from_where(where)
        if a is None:
            return []
        body = [a, 0x00, 0x1C, 0xE0] if what == '44' else [a, 0x00, 0x14, int(what)]
        return [[0xEC, iface, 0x00, 0x00] + body if iface is not None else body]
    if m.startswith('*1*') or m.startswith('*2*'):
        who, what, where = f[0], f[1], f[2]
        base, iface = _light_addr(where)
        if base is None:
            return []
        point = base[1] == 0 and base[0] not in (0xB1, 0xB3, 0xB5)
        if who == '1':
            if '#' in what:
                parts = what.split('#')
                if not all(x.isdigit() for x in parts):
                    return []
                if len(parts) == 2 and parts[0] in ('0', '1'):           # *1*1#N / *1*0#N*W## dimmer step
                    n = int(parts[1])
                    if (point or base[0] in (0xB1, 0xB3, 0xB5)) and n <= 255:
                        return [_light_ext_hdr(base, iface) + [0x42, 0x0D, 0x00 if parts[0] == '1' else 0x01, 0x00, n]]
                    return []
                if len(parts) == 3 and parts[0] in ('30', '31'):                  # *1*30#h#m / *1*31#h#m timers
                    h, mi = int(parts[1]), int(parts[2])
                    if 1 <= h <= 24 and mi <= 60:
                        return [_light_ext_hdr(base, iface) + [0x42, 0x0D, 0x03 if parts[0] == '30' else 0x04, h, mi]]
                    return []
                if len(parts) == 2 and parts[0] == '50' and parts[1] in ('9', '10'):   # *1*50#N*W##
                    body = base + [0x12, 0x96 + (int(parts[1]) - 9) * 0x10]
                    return [[0xEC, iface, 0x00, 0x00] + body if iface is not None else body]
                return []
            if what == '19':                                 # firmware bug: emits a 3-byte body
                body = base + [0x12]
                return [[0xEC, iface, 0x00, 0x00] + body if iface is not None else body]
            if not what.isdigit() or int(what) not in WHAT2VAL:
                return []
            vals = [WHAT2VAL[int(what)]]
        else:                                                # WHO 2 (coso)
            if what == '10':
                hdr = _cover_ext_hdr(base, iface)
                pa = hdr[0] == 0xD1 or (hdr[0] == 0xD5 and base[0] == 0xB3)
                return [hdr + [0x42 if pa else 0x32, 0x09, 0x09, 0x00, 0x00]]
            vals = {'0': [0x0A], '1': [0x0A, 0x08], '2': [0x0A, 0x09]}.get(what)
            if vals is None:
                return []
        for v in vals:
            body = base + [0x12, v]
            out.append([0xEC, iface, 0x00, 0x00] + body if iface is not None else body)
        return out
    if m.startswith('*#1*') or m.startswith('*#2*'):
        who, where, rest = f[0], f[1], f[2:]
        key = m
        if key in O2S:                                        # exact recorded command
            return [list(bytes.fromhex(x)) for x in O2S[key]]
        base, iface = _light_addr(where)
        if base is None:
            return []
        if who == '2' and rest:
            hdr = _cover_ext_hdr(base, iface)
            d = rest[0]; a = rest[1:]
            point_or_area = hdr[0] == 0xD1 or (hdr[0] == 0xD5 and base[0] == 0xB3)
            if d == '10' and not a:
                return [hdr + [0x43 if point_or_area else 0x33, 0x09, 0, 0, 0]]
            w = 0x42 if point_or_area else 0x32
            if d in ('#11', '#11#001') and len(a) == 1 and a[0].isdigit() and int(a[0]) <= 100:
                return [hdr + [w, 0x09, 0x39, int(a[0]), 0]]
            if d == '#12' and a == ['1']:
                return [hdr + [w, 0x09, 0x39, 0x6F, 0]]
            return []
        if not rest:
            body = base + [0x15, 0x00]
            return [[0xEC, iface, 0x00, 0x00] + body if iface is not None else body]
        hdr = _light_ext_hdr(base, iface)
        d = rest[0]; a = rest[1:]; na = len(a)
        if who == '1':
            r = _light_dim(hdr, d, a, na)
            if r is not None:
                return r
        # generalise recorded dimension commands over the address (recorded for WHERE 31)
        ad = addr_from_where(where.split('#')[0])
        if ad is not None and base[0] not in (0xB1, 0xB3, 0xB5):
            k31 = m.replace('*%s*' % where, '*31*', 1)
            if k31 in O2S:
                return [[ad if (i == 1 and x == 0x31) else x for i, x in enumerate(bytes.fromhex(b))] for b in O2S[k31]]
    return out


REQ_CODE = {'1': [0x0D, 0x0D], '2': [0x06], '4': [0x0D, 0x00], '5': [0x15], '6': [0x10], '7': [0x16],
            '8': [0x17], '12': [0x0C], '14': [0x0B], '15': [0x07]}


def _light_dim(hdr, d, a, na):
    """WHO 1 dimension request / write / state -> extended body, from bt_luci sweeps"""
    def fill(code, vals):
        body = hdr + code + vals
        return [body + [0] * (8 - len(body))] if len(body) <= 8 else None
    w = d.startswith('#'); dn = d.lstrip('#')
    if not w and na == 0 and dn in REQ_CODE:                          # request
        if dn == '15' and not (hdr[0] == 0xD5 and hdr[2] & 0x0F == 0x01 and hdr[2] >> 4 == 0):
            return []
        return fill([0x43] + REQ_CODE[dn], [])
    if not w and na == 0:
        return None
    ints = [int(x) for x in a] if all(x.isdigit() for x in a) else None
    if ints is None:
        return None
    t = 0x42 if w else 0x44                                            # write / state
    if not w and (dn not in ('12', '14', '15') or (dn == '15') != (hdr[0] == 0xD5) or (dn in ('12', '14') and hdr[0] != 0xD1)):
        return None
    if dn == '1' and na == 2 and 101 <= ints[0] <= 200 and ints[1] <= 255:
        return fill([t, 0x0D, 0x0D], [ints[0] - 100, ints[1]])
    if dn == '2' and na == 3 and ints[0] <= 24 and ints[1] <= 60 and ints[2] <= 60:
        return fill([t, 0x06], ints)
    if dn in ('5', '6') and na == 1 and ints[0] <= 255 and len(a[0]) <= 3:
        return fill([t, {'5': 0x15, '6': 0x10}[dn], 0x00, 0x00], [ints[0]])
    if dn == '8' and w and na == 1 and ints[0] == 0:
        return fill([t, 0x17, 0x00, 0x00], [0])
    if dn == '7' and na == 3 and ints[0] <= 24 and ints[1] <= 60 and ints[2] <= 60:
        return fill([t, 0x16], ints)
    if dn == '12' and na == 3 and ints[0] <= 359 and ints[1] <= 100 and ints[2] <= 100:
        return fill([t, 0x0C], [ints[0] & 0xFF, ints[1] | ((ints[0] >> 8) << 7), ints[2]])
    if dn == '14' and na == 1 and 1 <= ints[0] <= 1000:
        return fill([t, 0x0B], [ints[0] >> 8, ints[0] & 0xFF])
    if dn == '15' and na == 1 and ints[0] in (0, 1) and hdr[0] == 0xD5 and hdr[2] == 0x01:
        return fill([t, 0x07, 0x00, 0x00], [1 - ints[0]])
    return None


def own_to_scs(msg):
    """Returns the list of SCS wire frames the firmware emits for an OWN message."""
    m = msg.strip()
    who = m.strip('*#').split('*')[0]
    try:
        bodies = _dispatch(m, who)
    except (ValueError, IndexError, KeyError):
        bodies = []
    return [wire(bytes(b)) if len(b) in (4, 8) else ''.join('%02X' % x for x in b) for b in bodies]


def _dispatch(m, who):
    if who == '4':
        bodies = thermo_own.own_to_scs(m)
    elif who == '18':
        bodies = energy_own.own_to_scs(m)
    elif who in ('15', '25'):
        bodies = cen_own.own_to_scs(m)
    elif who in ('0', '9', '14'):
        bodies = _lights(m)
    elif who in ('1004', '1013'):
        bodies = device_own.own_to_scs(m)
    elif who == '22':
        bodies = sound_own.own_to_scs(m) or [list(bytes.fromhex(x)) for x in O2S.get(m, [])]
    elif who in ('1', '2'):
        bodies = _lights(m)
    elif m in O2S:
        bodies = [list(bytes.fromhex(x)) for x in O2S[m]]
    else:
        bodies = []
    return bodies


if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] not in ('hex', 'own'):
        print(__doc__); sys.exit(1)
    for a in sys.argv[2:]:
        r = scs_to_own(a) if sys.argv[1] == 'hex' else own_to_scs(a)
        print("%-40s -> %s" % (a, " + ".join(r) if r else "(no translation)"))
