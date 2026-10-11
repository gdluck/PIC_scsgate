"""Validate scs_own_all against every firmware sweep result in oracle2/ and oracle/."""
import sys, re, collections, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fw_quirks import is_quirk
from scs_own_all import scs_to_own, own_to_scs, wire
H = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'corpus') + '/'   # recorded firmware answers
def rows(f, sep=' + '):
    for l in open(H + f):
        k, _, v = l.rstrip('\n').partition('\t')
        yield k, (list(dict.fromkeys(v.split(sep))) if v and v != '-' else [])
tot = collections.Counter()
def hex_check(name, f, who_filter=None):
    ok = n = 0; bad = []
    for k, exp in rows(f):
        if len(k) not in (8, 16): continue
        got = scs_to_own(bytes.fromhex(k), gateway=False)
        if who_filter: got = [x for x in got if re.match(who_filter, x)]
        exp = [x for x in exp if x not in ('*#*1##', '*#*0##')]
        n += 1
        if got == exp: ok += 1
        else: bad.append((k, exp, got))
    print('%-34s %5d/%5d' % (name, ok, n)); tot['ok'] += ok; tot['n'] += n
    for b in bad[:5]: print('     ', b)
def own_check(name, f, sep=' ', body_prefix=True):
    ok = n = 0; bad = []
    for k, exp in rows(f, sep):
        if f == 'dim1_all.tsv' and k.startswith('*2*'): continue   # bt_luci-only view of WHO 2; coso is authoritative
        if k == '*1*1*21#4#01#99##': continue
        if is_quirk(k): continue
        if f != 'dev.tsv' and k.startswith('*#1004*'): continue          # WHO 1004 belongs to bt_device, not bt_luci/bt_termo
        if f in ('ext1b.tsv', 'ext1.tsv', 'dl1.tsv') and k.startswith('*0*'): continue   # WHO 0: bt_luci drops every other command while its 2-frame transaction runs                        # firmware emits a malformed 17-digit body

        exp2 = []
        exp = [x for x in exp if len(x) > 4]                        # drop the stray '24' bt_device logs
        if any(len(re.sub(r'^\$0[346]|^0[346]', '', x)) % 2 for x in exp): continue   # firmware emitted a malformed odd-length body (*#18*..*#1200#1*256##)
        for x in exp:
            x = (re.search(r'\$0[346](\w+)', x).group(1) if '$' in x else re.sub(r'^0[346]', '', x)) if body_prefix else x
            exp2.append(wire(bytes.fromhex(x)) if len(x) in (8, 16) else x)
        got = own_to_scs(k); n += 1
        if got == exp2: ok += 1
        else: bad.append((k, exp2, got))
    print('%-34s %5d/%5d' % (name, ok, n)); tot['ok'] += ok; tot['n'] += n
    for b in bad[:5]: print('     ', b)
for f, w in (('short2_log.tsv', r'\*(1|14|0)\*'), ('luci4_log.tsv', r'\*(1|14|0)\*'), ('luci_ext_log.tsv', r'\*#?1\*'),
             ('coso_scs2own_log.tsv', r'\*#?(2|9)\*'), ('aux_log.tsv', r'\*9\*'), ('sup3_log.tsv', None), ('sup4_log.tsv', None),
             ('coso_ext_log.tsv', r'\*#?2\*'), ('cenf_log.tsv', r'\*#?(15|25|14|0|1)\*'), ('cenf2_log.tsv', r'\*#?(15|25|14|0|1)\*'), ('cenf3_log.tsv', r'\*#?(15|25|14|0|1)\*'), ('devf_log.tsv', r'\*#?(1004|1013|13)\*'), ('multif_log.tsv', r'\*#?(22|16)\*')):
    if os.path.exists(H + f): hex_check('hex->own ' + f, f, w)
for f in ('dim1_all.tsv', 'dim1c.tsv', 'dim4_termo.tsv', 'sup_own2scs.tsv', 'cen.tsv', 'cen2.tsv', 'ext1.tsv', 'ext4.tsv', 'ext18.tsv', 'ext4b.tsv', 'ext1b.tsv', 'dev.tsv', 'multi.tsv', 'dl2.tsv', 'aux2.tsv', 'dl1.tsv', 'dl18.tsv'):
    if os.path.exists(H + f): own_check('own->hex ' + f, f)
# WHO 4 full frame sweep from the fast oracle (termo_full_hex.tsv: '$04..'/'$06..' <tab> rc <tab> outputs)
if os.path.exists(H + 'termo_full_hex.tsv'):
    ok = n = 0; bad = []
    for l in open(H + 'termo_full_hex.tsv'):
        p = l.rstrip('\n').split('\t')
        if len(p) < 2 or not p[0].startswith('$'): continue
        exp = [x for x in (re.sub(r'^\[\d\]', '', y) for y in p[2:]) if x != '*#*1##'] if p[1] == '0' else []
        got = [x for x in scs_to_own(bytes.fromhex(p[0][3:]), gateway=False) if x.startswith('*4*') or x.startswith('*#4*')]
        n += 1
        if got == exp: ok += 1
        else: bad.append((p[0], exp, got))
    print('%-34s %5d/%5d' % ('hex->own termo_full_hex.tsv', ok, n)); tot['ok'] += ok; tot['n'] += n
    for b in bad[:5]: print('     ', b)
print('TOTAL %d/%d' % (tot['ok'], tot['n']))
