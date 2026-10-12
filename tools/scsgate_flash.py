#!/usr/bin/env python3
"""Flash a PIC_scsgate board (PIC18F26K80 + MCP2200) through its own serial bootloader.

Wire protocol (both directions):  LL 10 07 <data...>   with LL = 2 + len(data)
  0x00 query -> 04 10 07 00 VV; 0x01 AL AH 40 new block, then 8 x (0A 10 07 b0..b7);
  0x02 CL CH end+write -> 08 10 07 02 RR CL CH cl ch (RR 00 ok, 01 protected, FE/FF checksum);
  0x03 CL CH end without write (no checksum check, verify with 0x55); 0x55 echo -> 40 + 64 bytes;
  0x80 reset.  On entry ('@' 0x11) the bootloader sends the query reply by itself.
Only 0x0000-0xEFFF is sent, pages are 64 bytes padded FF, page 0 last.
    scsgate_flash.py --port P --hex image.hex           # dry run (default)
    scsgate_flash.py --port P --hex image.hex --write   # dry run, then real pass
"""
import argparse, sys, time
try:
    import serial
except ImportError:
    sys.exit('pyserial missing: python3 -m pip install pyserial')

HOST, CMD_FIRMWARE, PAGE, APP_END, ENTER_BOOT = 0x10, 0x07, 64, 0xF000, b'@\x11'

def parse_hex(path):
    mem, skipped, ext = {}, {}, 0
    with open(path) as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line: continue
            if not line.startswith(':'): raise ValueError('%s:%d: not an Intel HEX record' % (path, n))
            rec = bytes.fromhex(line[1:])
            if sum(rec) & 0xFF: raise ValueError('%s:%d: record checksum error' % (path, n))
            ln, addr, typ, data = rec[0], int.from_bytes(rec[1:3], 'big'), rec[3], rec[4:-1]
            if ln != len(data): raise ValueError('%s:%d: bad record length' % (path, n))
            if typ == 1: break
            if typ == 4: ext = int.from_bytes(data, 'big') << 16
            elif typ == 2: ext = int.from_bytes(data, 'big') << 4
            elif typ == 0:
                for i, b in enumerate(data):
                    a = ext + addr + i
                    if a < APP_END: mem[a] = b
                    else:
                        region = ('bootloader F000-FFFF' if a < 0x10000 else 'config 0x300000' if a >> 16 == 0x30
                                  else 'EEPROM 0xF00000' if a >> 16 == 0xF0 else 'other 0x%06X' % (a & ~0xFFF))
                        skipped[region] = skipped.get(region, 0) + 1
            else: raise ValueError('%s:%d: unsupported record type %d' % (path, n, typ))
    if not mem: raise ValueError('%s: no program data in 0x0000-0xEFFF' % path)
    return mem, skipped

def pages_of(mem):
    starts = sorted({a & ~(PAGE - 1) for a in mem})
    if 0 in starts: starts.remove(0); starts.append(0)
    for s in starts: yield s, bytes(mem.get(s + i, 0xFF) for i in range(PAGE))

class Bootloader:
    def __init__(self, port, baud=115200, timeout=2.0, verbose=False):
        self.sp = serial.Serial(port, baud, timeout=timeout); self.verbose = verbose
        time.sleep(0.3); self.sp.reset_input_buffer()
    def _send(self, data):
        msg = bytes([2 + len(data), HOST, CMD_FIRMWARE]) + bytes(data)
        if self.verbose: print('  >', msg.hex(' '))
        self.sp.write(msg)
    def _read_reply(self):
        ll = self.sp.read(1)
        if not ll: raise IOError('timeout waiting for the bootloader reply')
        body = self.sp.read(ll[0])
        if len(body) != ll[0]: raise IOError('short reply: %s' % (ll + body).hex(' '))
        if self.verbose: print('  <', (ll + body).hex(' '))
        return body
    def _reply_data(self, cmd):
        body = self._read_reply()
        if len(body) < 3 or body[0] != HOST or body[1] != CMD_FIRMWARE or body[2] != cmd:
            raise IOError('unexpected reply to command %02X: %s' % (cmd, body.hex(' ')))
        return body[3:]
    def enter(self):
        self.sp.reset_input_buffer(); self.sp.write(ENTER_BOOT)
        return self._reply_data(0x00)[0]
    def query(self):
        self._send([0x00]); return self._reply_data(0x00)[0]
    def send_page(self, addr, data, write):
        assert len(data) == PAGE and addr & (PAGE - 1) == 0 and addr < APP_END
        self._send([0x01, addr & 0xFF, addr >> 8, PAGE])
        for i in range(0, PAGE, 8): self._send(data[i:i + 8])
        s = sum(data); cmd = 0x02 if write else 0x03
        self._send([cmd, s & 0xFF, s >> 8])
        return self._reply_data(cmd)
    def echo(self):
        self._send([0x55]); ll = self.sp.read(1)
        if not ll or ll[0] != PAGE: raise IOError('bad echo header: %s' % ll.hex())
        buf = self.sp.read(PAGE)
        if len(buf) != PAGE: raise IOError('short echo')
        return buf
    def reset(self): self._send([0x80]); self.sp.flush()
    def close(self): self.sp.close()

def run_pass(bl, pages, write):
    label = 'WRITE' if write else 'dry run'
    for n, (addr, data) in enumerate(pages, 1):
        r = bl.send_page(addr, data, write)
        if write:
            if len(r) != 5: raise IOError('page %04X: bad write reply %s' % (addr, r.hex(' ')))
            rr = r[0]
            if rr == 0x01: raise IOError('page %04X: protected area, refused by the bootloader' % addr)
            if rr in (0xFE, 0xFF): raise IOError('page %04X: checksum mismatch sent %02X%02X got %02X%02X' % (addr, r[2], r[1], r[4], r[3]))
            if rr != 0x00: raise IOError('page %04X: write status %02X' % (addr, rr))
        else:
            if bl.echo() != data: raise IOError('page %04X: echo differs from the data sent' % addr)
        print('\r%s page %d/%d  @%04X' % (label, n, len(pages), addr), end='', flush=True)
    print('\r%s: %d pages OK            ' % (label, len(pages)))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', required=True); ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--hex', required=True); ap.add_argument('--write', action='store_true')
    ap.add_argument('--no-reset', action='store_true'); ap.add_argument('-v', '--verbose', action='store_true')
    a = ap.parse_args()
    mem, skipped = parse_hex(a.hex); pages = list(pages_of(mem))
    print('%s: %d bytes in 0x%04X-0x%04X, %d pages of %d' % (a.hex, len(mem), min(mem), max(mem), len(pages), PAGE))
    for k, v in skipped.items(): print('  skipped %d bytes: %s' % (v, k))
    if 0 not in mem or 1 not in mem: sys.exit('refusing: the image has no reset vector at 0x0000')
    bl = Bootloader(a.port, a.baud, verbose=a.verbose)
    try:
        ver = bl.enter()
        print('bootloader entered, version 0x%02X (query again: 0x%02X)' % (ver, bl.query()))
        run_pass(bl, pages, write=False)
        if a.write:
            print('dry run passed; starting the real write (do not unplug!)')
            run_pass(bl, pages, write=True); print('flash complete')
        if not a.no_reset: bl.reset(); print('board reset')
    except Exception as e:
        print('\nERROR: %s' % e)
        print('the board is still in the bootloader; fix the problem and run again (page 0 is written last)' if a.write else 'nothing was written')
        sys.exit(1)
    finally:
        bl.close()

if __name__ == '__main__':
    main()
