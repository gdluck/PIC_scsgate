"""WHO 15 (CEN) and WHO 25 (CEN+) OWN -> SCS, from bt_luci (mhs1) sweeps."""
import re


def _addr(where):
    """CEN point/general/area address -> (frame_type, byte) or None"""
    if where == '0':
        return 0x04, 0x00
    if where.isdigit() and len(where) == 1:
        return 0x04, int(where)
    if where.isdigit() and len(where) == 2:
        return 0x03, int(where[0]) << 4 | int(where[1])
    if where.isdigit() and len(where) == 3 and where[:2] == '10':
        return 0x03, 0xA0 | int(where[2])
    if where.isdigit() and len(where) == 4 and int(where[:2]) < 16 and int(where[2:]) < 16 and (int(where[:2]) >= 10 or int(where[2:]) >= 10):
        a = int(where[:2]) << 4 | int(where[2:])
        if a != 0xFF:
            return 0x03, a
    return None


def own_to_scs(msg):
    m = msg.strip()
    f = m.strip('*#').split('*')
    if m.startswith('*15*'):
        what, where = f[1], f[2]
        iface = None
        mm = re.fullmatch(r'([^#]*)#4#(\d{2})', where)
        if mm:
            where, iface = mm.group(1), int(mm.group(2))
        a = _addr(where)
        if a is None:
            return []
        pre = [0xEC, iface, 0x00, 0x00] if iface is not None else []
        x = None
        if '#' in what:
            what, x = what.split('#')
            x = int(x)
        if not what.isdigit() or not (len(what) == 2 or int(what) >= 10):
            return []
        w = int(what)
        if x is None:
            return [pre + [0xCD, a[1], 0x14, w & 0xFF]]
        if 1 <= x <= 3 and w < 32:
            return [pre + [0xCD, a[1], 0x10, w | (x << 5)]]
        if x == 4 and w < 32:
            return [pre + [0xCD, a[1], 0x11, w | 0x20]]
        return []
    if m.startswith('*25*'):
        what, where = f[1], f[2]
        parts = what.split('#')
        w = int(parts[0]); ns = [int(p) for p in parts[1:]]
        zone, addr = where[0], where[1:]
        if zone == '2' and 21 <= w <= 28 and len(ns) == 1 and ns[0] <= 31 and addr.isdigit():
            v = int(addr)
            if v > 2047:
                return []
            return [[0xB2, v & 0xFF, 0x90 + w - 21, (ns[0] & 0x1F) | ((v >> 8) << 5)]]
        if zone == '1' and addr.isdigit():
            v = int(addr)
            if v > 255:
                return []
            if w in (11,) and len(ns) == 1:
                return [[0xB1, v, 0x93, ns[0]]]
            if w in (12, 15) and not ns:
                return [[0xB1, v, {12: 0x94, 15: 0x97}[w], 0x00]]
            if w in (13, 14) and len(ns) == 2:
                return [[0xB1, v, {13: 0x95, 14: 0x96}[w], ns[0]]]
            return []
        if zone == '3' and w in (31, 32) and ns in ([0], [1]) and re.fullmatch(r'\d{1,3}', addr) and int(addr) <= 100:
            return [[0xB4, 0x9A if addr == '100' else int(addr[-2:], 16), 0x91 + ns[0], w - 31]]
        return []
    if m.startswith('*#25*'):
        where = f[1]; rest = f[2:]
        if not rest and where[0] == '3' and re.fullmatch(r'\d{1,3}', where[1:]) and int(where[1:]) <= 100:
            return [[0xB4, 0x00, 0x90, 0x9A if where[1:] == '100' else int(where[1:][-2:], 16)]]
        return []
    return []
