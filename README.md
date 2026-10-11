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
bytes, and a validated SCS ⇄ OpenWebNet translator (`tools/`). The PIC code itself was corrected where
its interpretation of the bus disagreed with the firmware (see *Device table* below).

## Layout

| Path | Content |
|---|---|
| `ESPSCSGATE.C` | the application: UART command parser, SCS frame handling, device table, cover position tracking |
| `ESPSCSGATE_8266.H`, `_8285.H`, `_RASPY8.H` | board definitions (pins, UARTs); choose with `_ESP8266`, `_ESP8285`, `_RASPBERRY_8` |
| `SCS_*.INC`, `LIB/SCS_UART.ASM` | the bit-level SCS bus driver (interrupt driven, 10 frame receive buffer) |
| `LIB/CANREPRO_232_EVO*.ASM`, `canrepro.inc` | in-circuit firmware update over the UART |
| `espscsgate_RASPY_8.mcp`, `LIB/18F26K80_B.LKR` | MPLAB 8 project and linker script (Microchip C18 compiler) |
| `BIN/espscsgate_RASPY_8.hex` | a prebuilt image (upstream, version 543) |
| `tools/scs_own/` | SCS ⇄ OpenWebNet translator recovered from the MyHOMEServer1 firmware (C99 + Python), with its 26,809-frame test corpus |
| `tools/scsgate_own.py` | reads the gateway's serial output and prints the OpenWebNet messages for each frame |
| `tools/devtab_test/` | host build of the PIC's device-table classifier, replayed against the firmware corpus |

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
auxiliaries (WHO 9), `30`…`3F` heating (the low nibble is the probe / actuator index, the zone is in
`ss`), `81`/`83`/`8F` sound, `90`…`97` CEN+. Value byte `vv` for type `12`:

| `vv` | OpenWebNet | `vv` | OpenWebNet |
|---|---|---|---|
| `x0` | ON (`*1*1*`) | `x1` | OFF (`*1*0*`) |
| `x3` / `x4` (also `AB` / `BB`) | dimmer up / down (WHAT 30 / 31) | `1D`…`9D` | dimmer level 20…100 % (WHAT 2…10) |
| `0D` | ON | `0E`, `EE` | WHAT 19 |
| `16`…`86` | timers (WHAT 11…18) | `0B`, `1B`…`9B` | blinking (WHAT 20…29) |
| `08` / `09` / `0A` | cover up / down / stop (WHO 2) | `02`…`07`, `0C`, `0F` | unknown status (WHAT 255) |

The high nibble `x` is ignored by the firmware where shown. Extended frames `D1 aa ss kk DD b1 b2 b3`
carry dimensions (`ss` = system: `x1` lights/covers, `x2` energy, `x3` heating, high nibble = interface;
`kk` = `42` write, `43` request, `44` answer for lights; `02` / `03` / `34` for heating; `32` / `33` / `34`
for energy). `D2` is the general / answer form, `D5` area or group. Full tables, including every heating
dimension and the energy meter frames: `tools/scs_own/py/SCS_OWN_ALL_MAP.md`.

## Serial protocol (summary)

The UART runs at 115200 8N1 (`@^` 2 Mbaud, `@'` 500 kbaud, `@`+`0xED` 38400, `@`+`0xEE` 19200).
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
| `@W<len><bytes>` | write a complete frame (`K` in place of the checksum computes it) |
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
| `03` | dimmer | dimmer up / down, a level `1D`…`9D`, or a dimension 1 (level + speed) frame |
| `08` | cover | up / down / stop, or a cover position frame (dimension `09`) |
| `09` | cover with position tracking | set by `@U` |
| `0E` | alarm | type bytes `43`, `44`, `49`, `4E` (upstream rule, not from the firmware) |
| `0F` | heating zone | any short frame of type `30`…`3F` (zone in the second byte), or an extended heating frame |
| `10` | energy meter | extended frames with system `02` (address `A0\|N` = WHERE `5N`) |

Rules that changed in this fork, each contradicted by the firmware corpus before the change:

* `B5 0N 12 vv` (group command) was recorded as device `0N`; `B3` (area) likewise; groups and areas are
  not devices.
* `x0` / `x1` with a non-zero high nibble were ignored; the firmware reads them as ON / OFF.
* `0D` was taken as a dimmer level; it is a plain ON. Dimmer levels are `1D`…`9D` only.
* `03` / `04` (dim up / down) were matched exactly; the firmware ignores the high nibble, and `AB` / `BB` mean the same.
* Heating zones were detected only in `B4 ZZ 30 vv` frames and only for zones below 15. All short
  heating frames carry the zone, and zone numbers go to 255 (99 in OpenWebNet terms, `0x80|Z` for actuators).
* Extended frames (`D1 …`) were ignored for the table; they now identify dimmers, covers, heating zones
  and energy meters.

`tools/devtab_test` compiles the classifier straight out of `ESPSCSGATE.C` and replays the corpus
through it: 7,259 frames carry a verifiable expectation, and all 7,259 match (upstream: 742).

## Tools

```sh
# live: what the bus is saying, in OpenWebNet
python3 tools/scsgate_own.py --port /dev/ttyUSB0          # after @MA @l on the gateway
# offline: a captured log
python3 tools/scsgate_own.py capture.txt
# the other direction: which frame to write for an OpenWebNet command
python3 tools/scsgate_own.py --own '*1*1*31##'            # -> A8 31 00 12 00 23 A3, send with @W7A83100120023A3

# tests
make -C tools/scs_own test        # C translator vs corpus: 26809/26809
make -C tools/devtab_test test    # PIC classifier vs corpus: 7259/7259
```

## Building the PIC image

MPLAB 8 with the Microchip C18 compiler, project `espscsgate_RASPY_8.mcp`. Define one of `_ESP8266`,
`_ESP8285`, `_RASPBERRY_8` (and `_BOOTMODE` for the bootloader layout) in the project settings. The
changes in this fork are plain C89 in `ESPSCSGATE.C` only; the bus driver and the build are untouched.
