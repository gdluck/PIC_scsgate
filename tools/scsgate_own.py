#!/usr/bin/env python3
"""Translate PIC_scsgate output into OpenWebNet, live or from a log.

The PIC gateway prints every SCS frame it hears on its serial port.  This script reads that
output and prints the OpenWebNet message(s) the BTicino MyHOMEServer1 firmware would emit for
the same frame, using the firmware-derived translator in scs_own/py (validated on 26,809
recorded firmware answers).

Accepted input formats (one frame per line, anything else is echoed unchanged):

    SCS[7]:  A8 B8 31 12 00 9B A3        ascii log mode (@MA @l)
    7A8B83112009BA3                       ascii read mode (@MA @r / @R)
    A8 B8 31 12 00 9B A3                  plain hex, with or without spaces
    B8311200                              bare body (as in hex2own_corpus.tsv)

Hex mode (@MX) sends raw bytes: a length byte followed by the frame.  Pass --raw to decode
that stream (from a serial port or a captured file).

Examples:

    python3 scsgate_own.py --port /dev/ttyUSB0 --baud 115200
    python3 scsgate_own.py < capture.txt
    echo 'A8 B8 31 12 00 9B A3' | python3 scsgate_own.py
    python3 scsgate_own.py --own '*1*1*31##'        # the other direction: OWN -> frame to send with @W

Needs only Python 3; --port needs pyserial (pip install pyserial).
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'scs_own', 'py'))
import scs_own_all  # noqa: E402

HEX_RE = re.compile(r'(?:[0-9A-Fa-f]{2}[ \t]*){4,16}')


def frame_from_line(line):
    """Return the hex body of the frame on this line, or None."""
    s = line.strip()
    m = re.search(r'SCS\[([0-9A-Fa-f])\]:\s*([0-9A-Fa-f ]+)', s)
    if m:
        return m.group(2)
    m = re.fullmatch(r'([1-9A-Fa-f])([0-9A-Fa-f]+)', s.replace(' ', ''))
    if m and int(m.group(1), 16) * 2 == len(m.group(2)):   # ascii read mode: length nibble + bytes
        return m.group(2)
    m = HEX_RE.search(s)
    if m and len(re.sub(r'\s', '', m.group(0))) in (8, 14, 16, 22):
        return m.group(0)
    return None


def translate(hexframe):
    try:
        body = scs_own_all.parse_hex(hexframe)
    except Exception:
        return None
    if body is None:
        return None
    try:
        msgs = scs_own_all.scs_to_own(body)
    except Exception as e:  # a frame the firmware would crash on; keep going
        return ['(translator error: %s)' % e]
    return msgs or []


def run_lines(lines, out):
    for line in lines:
        line = line.rstrip('\r\n')
        hx = frame_from_line(line)
        if hx is None:
            out.write(line + '\n')
            continue
        msgs = translate(hx)
        if msgs is None:
            out.write('%-40s -> (not an SCS frame)\n' % line)
        elif not msgs:
            out.write('%-40s -> (no OpenWebNet mapping)\n' % line)
        else:
            out.write('%-40s -> %s\n' % (line, ' + '.join(msgs)))
        out.flush()


def run_raw(stream, out):
    """Hex mode: <len><bytes...>; 0x00 = empty answer; 'k'/'E' answers and the banner are passed through.

    The stream is resynchronised on <len> A8 ... A3 (len 7 or 11), so a stray answer byte or a
    partial read does not shift every following frame.
    """
    buf = b''
    while True:
        chunk = stream.read(1)
        if not chunk:
            return
        buf += chunk
        while buf:
            n = buf[0]
            if n in (7, 11) and len(buf) >= 2 and buf[1] != 0xA8:
                buf = buf[1:]
                continue
            if n not in (7, 11):
                buf = buf[1:]
                continue
            if len(buf) < 1 + n:
                break                       # wait for the rest of the frame
            frame = buf[1:1 + n]
            if frame[-1] != 0xA3:
                buf = buf[1:]               # not a frame: skip the length byte and resync
                continue
            buf = buf[1 + n:]
            hx = ' '.join('%02X' % x for x in frame)
            msgs = translate(hx)
            out.write('%-40s -> %s\n' % (hx, ' + '.join(msgs) if msgs else '(no OpenWebNet mapping)'))
            out.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', help='serial port of the gateway (needs pyserial)')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--raw', action='store_true', help='input is the binary hex-mode stream (@MX)')
    ap.add_argument('--own', nargs='+', metavar='MSG', help='translate OpenWebNet messages into SCS frames instead')
    ap.add_argument('files', nargs='*', help='log files to translate (default: stdin)')
    a = ap.parse_args()

    if a.own:
        for msg in a.own:
            frames = scs_own_all.own_to_scs(msg)
            if not frames:
                print('%-40s -> (the firmware sends nothing for this message)' % msg)
                continue
            for fr in frames:            # wire frames: "A8 .. CHK A3" (or a bare hex string for odd frames)
                digits = re.sub(r'[^0-9A-Fa-f]', '', fr)
                print('%-40s -> %s' % (msg, fr))
                # the gateway's @W command takes the whole wire frame: @W<len><bytes>  (ascii mode)
                print('%40s    send with: @W%X%s' % ('', len(digits) // 2, digits.upper()))
        return

    if a.port:
        try:
            import serial
        except ImportError:
            sys.exit('pyserial is required for --port: pip install pyserial')
        with serial.Serial(a.port, a.baud, timeout=1) as sp:
            if a.raw:
                run_raw(sp, sys.stdout)
            else:
                def lines():
                    buf = b''
                    while True:
                        chunk = sp.read(256)
                        if not chunk:
                            continue
                        buf += chunk
                        while b'\n' in buf:
                            l, buf = buf.split(b'\n', 1)
                            yield l.decode('latin-1')
                run_lines(lines(), sys.stdout)
        return

    if a.raw:
        src = open(a.files[0], 'rb') if a.files else sys.stdin.buffer
        run_raw(src, sys.stdout)
        return
    if a.files:
        for f in a.files:
            with open(f, encoding='latin-1') as fh:
                run_lines(fh, sys.stdout)
    else:
        run_lines(sys.stdin, sys.stdout)


if __name__ == '__main__':
    main()
