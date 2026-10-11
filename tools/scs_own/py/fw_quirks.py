"""Firmware behaviours a deterministic translator cannot reproduce; shared by validate_all.py and diff_check.py.
is_quirk(msg) -> True when the row must be skipped in a comparison."""
import re


def _where(msg, f):
    """OWN fields (without the leading '*' / trailing '##') -> WHERE"""
    return f[1] if msg.startswith('*#') else (f[2] if len(f) > 2 else '')


def is_quirk(msg):
    f = msg.strip().strip('*#').split('*')
    who = msg.lstrip('*#').split('*')[0]
    if who == '18':
        return bool(re.search(r'\*#1200#1\*256##$', msg))            # bt_supervisione emits a malformed 17-digit body
    if who != '4':
        return False
    w = _where(msg, f)
    if msg.startswith('*#4*') and len(f) > 2 and f[2].startswith('#7') and len(f) > 3 and '*'.join(f[3:5]) in ('0*0', '3*5', '1*5', '2*5', '3*31', '2*31', '2*32'):
        return True                                                 # bt_termo #7 pairs coded 00: byte 2 is 00 or 0C depending on internal state
    p = w.split('#')
    if p[0] == '':                                                  # '#0#N' / '#N'
        nums = [int(x) for x in p[1:] if x.isdigit()]
        return any(n > 255 for n in nums[:2])                       # central / group numbers above 255 wrap
    if len(p) == 2 and p[0].isdigit() and p[1].isdigit():
        return int(p[0]) >= 128 or int(p[1]) >= 16                  # actuator zone / number overflow into the next byte
    return p[0].isdigit() and len(p[0]) >= 4                        # 4-digit WHERE is taken as a 16-bit value
