"""WHO 1004 (device diagnostics) and WHO 1013 (gateway diagnostics) OWN -> SCS, from bt_device (mhs1)."""
import re

DIM33 = {1: 0x80, 2: 0x81, 3: 0x82, 4: 0x83, 5: 0x84, 6: 0x85, 7: 0x86, 8: 0x87, 10: 0x8E, 11: 0x89, 12: 0x8A}


def _addr(where):
    """WHERE -> (header byte 0, address byte, header byte 2) ; decimal device number, 12 bits"""
    where = re.sub(r'#4#\d+$', '', where)
    if where == '0':
        return 0xD2, 0x00, 0x03
    if where.startswith('#') and where[1:].isdigit():
        return 0xD1, 0x00, 0x03
    if where.isdigit() and int(where) < 4096:
        n = int(where)
        return 0xD1, n & 0xFF, 0x03 | ((n >> 8) << 4)
    return None


def own_to_scs(msg):
    m = msg.strip(); f = m.strip('*#').split('*')
    if m.startswith('*#1004*') and len(f) == 3 and f[2].isdigit():
        a = _addr(f[1])
        if a is None:
            return []
        h, aa, b2 = a
        d = int(f[2])
        if d == 13:
            return [[0xD0, 0x00, 0x03, 0xF3, 0, 0, 0, 0]]
        if d == 0:
            return [[h, aa, b2, 0x32, 0x8C, 0x00, 0x01, 0]]
        if d in DIM33:
            return [[h, aa, b2, 0x33, DIM33[d], 0, 0, 0]]
        if d in (20, 23):
            return [[h, aa, b2, 0x03, 0x8F, 0x00, 0xFF if d == 20 else 0x64, 0]]
        return []
    if m.startswith('*#1013**') and len(f) == 3 and f[2].isdigit():
        d = int(f[2])
        if d in (6, 8, 10, 11):
            return [[0xD2, 0x00, 0x0F, 0x03, DIM33[d], 0, 0, 0]]
        return []
    if m == '*1013*1*0##':
        return [[0xD2, 0x00, 0x0F, 0x02, 0x8C, 0, 0, 0]]
    return []
