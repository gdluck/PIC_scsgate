# PIC_scsgate

Firmware for a PIC18F26K80 that sits on the BTicino / Legrand **SCS** two-wire bus (MyHOME) and
exposes it on a UART: every bus frame is reported, any frame can be written, and the gateway keeps a
small table of the devices it has seen. An ESP8266 / ESP8285 or a Raspberry Pi talks to it over that
UART and does the network side (the companion firmware is not part of this repository).

Author of the gateway and its bus driver: Guido Pagani (guidopic@altervista.org,
http://guidopic.altervista.org). See the licence notes at the top of `ESPSCSGATE.C`: hobby use only,
no commercial use and no redistribution without the author's consent.

This fork adds what was learned by running the original BTicino **MyHOMEServer1** gateway programs
(`bt_luci`, `coso`, `bt_termo`, `bt_supervisione`, …) on an emulated bus: the exact meaning of the SCS
bytes, and a validated SCS ⇄ OpenWebNet translator (`tools/`). The F454, F459, F461 and F450 firmwares
put the same bytes on the bus. The PIC code itself was corrected where its interpretation of the bus
disagreed with the firmware (see *Device table* below), and its bus write retry was fixed (see *Bus
writes and thermostats*).

## Layout

| Path | Content |
|---|---|
| `ESPSCSGATE.C` | the application: UART command parser, SCS frame handling, device table, cover position tracking |
| `ESPSCSGATE_8266.H`, `_8285.H`, `_RASPY8.H` | board definitions (pins, UARTs); choose with `_ESP8266`, `_ESP8285`, `_RASPBERRY_8` |
| `SCS_*.INC`, `LIB/SCS_UART.ASM` | the bit-level SCS bus driver (interrupt driven, 10 frame receive buffer) |
| `LIB/CANREPRO_232_EVO*.ASM`, `canrepro.inc` | in-circuit firmware update over the UART |
| `espscsgate_RASPY_8.mcp`, `LIB/18F26K80_B.LKR` | MPLAB 8 project and linker script (Microchip C18 compiler) |
| `BIN/espscsgate_RASPY_8.hex` | a prebuilt image (upstream, version 543) |
| `tools/scs_own/` | SCS ⇄ OpenWebNet translator recovered from the MyHOMEServer1 firmware (C99 + Python), with the 26,809-frame corpus and the 111,820 recorded firmware answers it is validated against |
| `tools/scsgate_own.py` | reads the gateway's serial output and prints the OpenWebNet messages for each frame |
| `tools/devtab_test/` | host build of the PIC's device-table classifier, replayed against the firmware corpus |
| `tools/scsgate_flash.py` | writes a hex image into the board through its serial bootloader (see *Flashing over USB*) |
| `tools/build_mplab8.bat` | command-line build with MPLAB 8 + C18, mirroring the `.mcp` project |

## SCS frames, as the firmware sees them

```
A8 <body> <chk> A3        chk = XOR of the body bytes
body = 4 bytes (short frame)  or  8 bytes (extended frame)
A5                        acknowledge sent by the addressed device
```

Short frame `dd ss tt vv`:

| `dd` | meaning | `ss` |
|---|---|---|
| `01`…`AF` | point-to-point command to address `dd` (area nibble, point nibble: `31` = A3 PL1, `0F` = `0015`, `A5` = `1005`) | sender |
| `B8` | status broadcast | the address reporting |
| `B1 00` | general command (all) | |
| `B3 0A` | area A | |
| `B5 0N` | group N | |
| `EC ii 00 00 dd ss tt vv` | the same frame routed through bus interface `ii` (8-byte body) | |

Type byte `tt`: `12` command / status for lights and covers, `15` status request (`dd 00 15 00`),
`10` / `11` unlock / lock an actuator (WHO 14), `17` and `1C` scenario modules (WHO 0), `9A`…`9C`
auxiliaries (WHO 9), `30`…`3F` heating (see below), `81`/`83`/`8F` sound, `90`…`97` CEN+. Value byte
`vv` for type `12`:

| `vv` | OpenWebNet | `vv` | OpenWebNet |
|---|---|---|---|
| `x0` | ON (`*1*1*`) | `x1` | OFF (`*1*0*`) |
| `x3` / `x4` (also `AB` / `BB`) | dimmer up / down (WHAT 30 / 31) | `1D`…`9D` | dimmer level 20…100 % (WHAT 2…10) |
| `0D` | ON | `0E`, `EE` | WHAT 19 |
| `16`…`86` | timers (WHAT 11…18) | `0B`, `1B`…`9B` | blinking (WHAT 20…29) |
| `08` / `09` / `0A` | cover up / down / stop (WHO 2) | `02`…`07`, `0C`, `0F` **as a status** (`B8`) | unknown status (WHAT 255) |

The high nibble `x` is ignored by the firmware where shown. Note the asymmetry: `03` / `04` are dimmer
up / down when sent as a command, but reported by a device (`B8 dd 12 03`) they are "unknown status",
while `13`, `23` … `F3` and `AB` keep the dimmer meaning in both directions. `06` is ON as a command.

Heating frames `dd zz 3N vv` (WHO 4): `zz` is the zone, `N` the probe / actuator index. `B4` / `B5` are
the measured temperature reported by the zone probe, `90` / `91` / `92` the set point written to the zone,
`93` and `9F` / `BF` mode commands, `96` actuator command and `B7` actuator status, `9D` / `9E` events;
`99`, `A6`, `A9` are the requests the central unit sends (also to zones that do not exist). When bit 7
of `zz` is set and `N` is not 0, the frames `96` `99` `9D` `9E` `B7` address actuator `N` of zone
`zz & 0x7F` (`B7 80 31 01` = `*#4*0#1*20*0##`); in `B4` `B5` `90`…`93` the byte is used whole
(`B4 80 31 E6` = zone 128, which does not exist in OpenWebNet). With bit 7 clear, `N` is a probe index
(`B4 28 31 00` = probe 1 of zone 40, `*#4*140*…`), except in `90`…`93` where it is ignored.

Extended frames `D1 aa ss kk DD b1 b2 b3` carry dimensions: `aa` is the address (`D1` command / request to
a point, `D2` answer from a point; `D2 00` general, `D5` area or group), `ss` the system (`x1` lights and
covers, `x2` energy, `x3` heating; the high nibble is the bus interface for lights and the probe / actuator
index for heating), `kk` the kind (low nibble `2` write, `3` request, `4` answer: `42` / `43` / `44` lights,
`02` / `03` / `34` heating, `32` / `33` / `34` energy). Energy meters are `aa = A0|N` (WHERE `5N`);
heating dimension bytes `C1` / `C2` are central-unit forms (`#0#N`, `#N`), where `aa` is not a zone. Full
tables, including every heating dimension and the energy meter frames: `tools/scs_own/py/SCS_OWN_ALL_MAP.md`.

## Serial protocol (summary)

The UART runs at 115200 8N1 (`@^` 2 Mbaud, `@9` 500 kbaud, `@`+`0xED` 38400, `@`+`0xEE` 19200).
Commands start with `@`; in **ascii mode** parameters are hex digits, in **hex mode** they are raw bytes.
Most commands answer `k` (ok) or `E` (error).

| Command | Effect |
|---|---|
| `@MA` / `@MX` | ascii / hex mode (stored in EEPROM) |
| `@l` | continuous log: every received frame is sent to the UART (`SCS[7]:  A8 B8 31 12 00 9B A3` in ascii mode, `<len><bytes>` in hex mode) |
| `@r` / `@R` | read one frame from the receive queue now / when one arrives (`0` = queue empty in ascii mode) |
| `@b` | clear the receive queue |
| `@F0`…`@F8` | filter bits: 1 drop repeated frames, 2 drop `A5` acks, 4 drop status frames, 8 accept wrong checksums |
| `@A`/`@B` `[i|e][n][vv]` | byte filters: include / exclude frames whose byte `n` equals `vv` |
| `@Y0`…`@Y3` | short form: 1 omit `A8`, checksum and `A3` when reporting, 2 when writing, 3 both |
| `@W<len><bytes>` | write a complete frame; `len` is **one hex digit** (`7` for a short frame, `B` for an 11-byte extended frame: `@WBA8D1…A3`, never `@W11…`); `K` in place of the checksum computes it |
| `@y<4 bytes>` | write a short frame body; `A8`, checksum and `A3` are added |
| `@X<8 bytes>` | write an extended body (routed `EC …` frames; sent as a short frame when the bus id is the local one) |
| `@w<vv><dd>` | point command: `A8 dd 00 12 vv chk A3` |
| `@x<vv><ii><dd>` | the same through interface `ii` |
| `@t<dd>` | status request `A8 dd 00 15 00 chk A3` |
| `@D<dd>` | walk the device table from address `dd` (`FF` clears it); answers `D <addr> <type>` |
| `@z` | dump the device table (ascii mode) |
| `@u<dd><pct>`, `@U<opt>` | covers with position tracking (see the comments in the source) |
| `@P` / `@N` / `@n` | auto-acknowledge point commands for addresses `01`…`AF` / `80`…`9F` / off |
| `@q`, `@Qr` | version, restart counter |
| `@o`, `@`+`0x17` | presets: monitor (ascii, no filter) / http (hex, filter 3, short form, log) |
| `@E`, `@\|\|` | reset EEPROM, reset the PIC |

## Device table

The gateway learns device types from the traffic it hears and reports them with `@D` / `@z`:

| Type | Meaning | Learned from |
|---|---|---|
| `01` | switch | any WHO 1 frame to or from the address (ON / OFF, timers, blinking, …), if the address is still unknown |
| `03` | dimmer | dimmer up / down or a level `1D`…`9D` (command, or `13`…`F3` / `AB` / `BB` as status), or a dimension 1 (level + speed) write / answer |
| `08` | cover | up / down / stop, or a cover position write / answer (dimension `09`) |
| `09` | cover with position tracking | set by `@U` |
| `0E` | alarm | type bytes `43`, `44`, `49`, `4E` (upstream rule, not from the firmware) |
| `0F` | heating zone (1…99) | `B4` `B5` `96` `B7` `9D` `9E` `9F` `BF` `90`…`93` short frames (zone in the second byte), or an extended heating write / answer; not from the requests `99` `A6` `A9` |
| `10` | energy meter | extended energy write / answer with address `A1`…`AF` (WHERE `51`…`515`) |

Rules that changed in this fork, each contradicted by the firmware corpus before the change:

* `B5 0N 12 vv` (group command) was recorded as device `0N`; `B3` (area) likewise. Groups and areas are
  not devices. Area cover commands (`B3 0A 12 08/09/0A`) now move the tracked covers of area `A`
  (`CmdGruppoTapparelle`); group membership is not visible on the bus, so `B5` cannot be applied.
* `x0` / `x1` with a non-zero high nibble were ignored; the firmware reads them as ON / OFF.
* `0D` was taken as a dimmer level; it is a plain ON. Dimmer levels are `1D`…`9D` only.
* `03` / `04` were matched exactly as dimmer up / down. As commands the firmware ignores the high nibble
  (`13`, `23`, `AB` …); as a status (`B8 dd 12 03`) they are "unknown", and no type is recorded.
* Heating zones were detected only in `B4 zz 30 vv` frames and only for zones below 15. Zones 1…99 are now
  read from every frame a zone emits or is written with (see the frame notes above); requests are ignored,
  as the status request `15` is for lights, because the central unit also polls zones that do not exist.
* Extended frames were ignored for the table; `D1` / `D2` writes and answers now identify dimmers, covers,
  heating zones and energy meters. Requests (`kk = x3`) do not, for the same reason.

Zones and light addresses share the same byte values (zone 40 is `0x28`, which is also A2 PL8). The table
has one entry per byte, so the first type seen wins between switch, heating zone and energy meter;
dimmer and cover evidence (level / position frames) still overrides, as upstream. `@DFF` clears the table.

`tools/devtab_test` compiles the classifier straight out of `ESPSCSGATE.C` and replays the corpus
through it. The expected type of each frame is derived from the OpenWebNet text the firmware emitted for
it (WHO, WHAT and WHERE), not from the classifier's rules: 19,549 of the 26,809 frames carry such an
expectation and all 19,549 match (the upstream classifier: 2,616). The same harness checks the area
cover command against tracked covers.

## Bus writes and thermostats

`queueWrite` retried a frame up to 50 times after a collision with all interrupts still disabled, so the
"wait for a free bus" loop before each retry could not see the frame it had collided with (the receive
flag it polls is set by an interrupt) and fired again after 4 ms, in the middle of the other device's
frame, a few stray pulses at a time. KW4691 / 4691 thermostats, which talk to their actuator and central
unit in long extended-frame dialogues, are the devices most exposed to this: a corrupted exchange with
their actuator puts them in error. The retry loop now re-enables interrupts after every attempt, also
looks at the bus level itself (`INPUT_SCS`), waits longer after each collision (8, 12, 16 … ms of
silence) and gives up after 10 attempts instead of 50. The change is in C only (`queueWrite`); the
bit-level driver in `LIB/SCS_UART.ASM` is untouched. It has not been run on a bench: it is a logic
fix, and the description above is what the code did before.

## Notes for host software

* `@W` takes a single hex digit as length: `@W7A8…A3` for short frames, `@WBA8…A3` for extended ones.
  `@W11A8…` is read as length 1 and writes the single byte `1A` on the bus.
* Zone status request: `*#4*Z##` → `A8 99 Z 30 00 chk A3` (the firmware also sends `99 Z 30 12`, `0E`, `0D`).
* Set point: `*#4*Z*#14*TTTT*M##` → `A8 90|91|92 Z 30 T chk A3` (`90` heating, `91` cooling, `92`
  generic; `T` = temperature in half degrees, `0230` → `2E`). Mode: `*4*303*Z##` (off) →
  `93 Z 30 0F`, `*4*102*Z##` (antifreeze) → `93 Z 30 02`, `*4*202*Z##` (thermal protection) → `93 Z 30 03`.
  `D2 Z 03 34 12 …` and `B7 Z 30 …` are answers / status reports from the zone, not commands.
  `python3 tools/scsgate_own.py --own '<message>'` prints the frame and the `@W` command for it.

## Tools

```sh
# live: what the bus is saying, in OpenWebNet
python3 tools/scsgate_own.py --port /dev/ttyUSB0          # after @MA @l on the gateway
# offline: a captured log
python3 tools/scsgate_own.py capture.txt
# the other direction: which frame to write for an OpenWebNet command
python3 tools/scsgate_own.py --own '*1*1*31##'            # -> A8 31 00 12 00 23 A3, send with @W7A83100120023A3

# tests
make -C tools/scs_own test                  # C translator vs corpus: 26809/26809
python3 tools/scs_own/py/validate_all.py    # Python translator vs every recorded firmware answer: 111820/111820
make -C tools/devtab_test test              # PIC classifier vs corpus: 19549/19549 + cover area test
```

## Building the PIC image

MPLAB 8 with the Microchip C18 compiler, project `espscsgate_RASPY_8.mcp`. Define one of `_ESP8266`,
`_ESP8285`, `_RASPBERRY_8` (and `_BOOTMODE` for the bootloader layout) in the project settings. The
changes in this fork are plain C89 in `ESPSCSGATE.C` only (version 544); the bus driver and the build are untouched.

The board tells which variant it runs: `@q` answers `SCS 80.543` for a `_RASPBERRY_8` build (`85.` =
ESP8285, `66.` = ESP8266, `70.` = Raspberry 7; a trailing `B` = `_BOOTMODE`). The USB boards with an MCP2200
bridge answer `80.` and build from the RASPY_8 project.

Both tools exist for Windows only (MPLAB IDE 8.92 and MPLAB C18 v3.47 lite, from Microchip's archives;
the `.mcp` points at C18 v3.46, with every optimisation switched off, which the free lite edition
reproduces). `tools/build_mplab8.bat` runs the same command lines MPLAB 8 generates for the project
(`wine cmd /c tools\build_mplab8.bat` under Wine) and `tools/build_wine.sh` runs them through Wine
directly, both from the repository root; the objects go to `OBJ/`, the hex to `BIN/`.

What worked on macOS, without a system install: a Wine build with 32-bit support (Wine 10 or later;
the Gcenx "Wine stable" build unpacked into a folder), the `MPASM Suite` taken out of the MPLAB 8.92
installer's MSI (`msiexec /a`, no IDE needed) and C18 v3.47 lite from the Wayback Machine, since
microchip.com refuses the direct link. Its BitRock installer in unattended mode installs everything
except the compiler itself (`mcc18.exe`, `mcc18-traditional.exe`, `mcc18-extended.exe` belong to a
component only the GUI selects): take them out of the installer payload with `bitrock-unpacker` and
drop them into `bin`. Then `WINE=... WINEPREFIX=... tools/build_wine.sh`.

The toolchain was proven before building anything new: the untouched 543 source rebuilt this way is
byte-for-byte identical to `BIN/espscsgate_RASPY_8.hex` (`tools/compare_hex.py`, 0 differing bytes in
every region). The 544 build is 30320 bytes at `0000`-`7673` (474 pages), with the bootloader region
and config words identical to 543; it answers `@q` with `SCS 80.544`.

## Flashing over USB

The image carries its own bootloader at `F000`-`FFFF` (`LIB/CANREPRO_232_EVO.ASM`), which the running
firmware enters on the two bytes `@` `0x11` at the current UART speed. `tools/scsgate_flash.py` drives it:

```sh
python3 tools/scsgate_flash.py --port /dev/cu.usbmodemXXXX --hex BIN/espscsgate_RASPY_8.hex          # dry run
python3 tools/scsgate_flash.py --port /dev/cu.usbmodemXXXX --hex BIN/espscsgate_RASPY_8.hex --write  # dry run, then write
```

Every message, in both directions, is `LL 10 07 data…` with `LL` = 2 + number of data bytes (`10` = host
address, `07` = firmware command): `00` query → `04 10 07 00 xx` (the bootloader also sends this on entry);
`01 AL AH 40` opens a 64-byte page at flash address `AHAL`, followed by the 64 bytes as eight messages of
eight data bytes; `02 CL CH` closes it with the 16-bit sum of the bytes and writes → `08 10 07 02 RR CL CH cl ch`
with `RR` `00` written, `01` protected (`F000`-`FFFF`), `FE`/`FF` checksum mismatch; `03 CL CH` closes without
writing (and without checking); `55` echoes the page buffer (`40` + 64 bytes); `80` resets the board. The
tool sends only `0000`-`EFFF` (the config words at `300000` and the EEPROM at `F00000` would wrap onto
address 0), pads pages with `FF`, writes page 0 last, waits for every reply and stops at the first error.
`--write` runs the complete dry run first (every page echoed back and compared) and only then writes.

A write that stops half-way leaves the board without a working program, and the bootloader is only
reachable from that program: keep the cable still, and keep a PICkit at hand for that case. The second
byte of the query answer is not the version: `ReproQuery` stores `REPRO_VERSION` one byte beyond the two
it sends, so it only shows as the fourth data byte of the first `03` reply (`08 10 07 03 xx xx 1B xx xx`),
and the boards seen so far carry `1B`, the version of the source here. The 544 image was put on a board
this way (dry run, then 474 pages written and acknowledged, board reset, bootloader entered again from
the new firmware).
