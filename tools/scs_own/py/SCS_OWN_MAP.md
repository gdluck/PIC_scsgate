# SCS ⇄ OpenWebNet (WHO 4, thermoregulation): mapping taken from the firmware

Source of truth: `mhs1/home/bticino/bin/bt_termo` (ARM32 Thumb-2, stripped), run under
qemu in Docker (`arm32v7/gcc:10`). The SCS→OWN translator is the function at file offset
**0x9050** (`int tr(openwebnet **out, const char *frame)`); `oracle/hook2.c` calls it
directly. OWN→SCS was captured by feeding OWN strings to bt_termo's TCP port and logging
what it sends to a stub scsserver. Every row below is observed firmware output, not guessed.

Tools in `oracle/`:
- `bt_oracle.py hex <frames…>` and `bt_oracle.py own <cmds…>` run the firmware in both directions.
- `hex2own_firmware.tsv` holds 11,311 frames the firmware accepted, with their OWN output.
- `own2hex_table.tsv` holds OWN commands and the SCS frames bt_termo emits for them.

## 1. Wire framing

```
A8 <body…> <CHK> A3      CHK = XOR of the body bytes
body = 4 bytes (short / "brief" frame)  or  8 bytes (extended frame)
```
Internally, and in scsserver's client protocol, frames appear as `$04<body>` (short) and
`$06<body>` (extended). scsserver sends `*02*01*A8<body><CHK>` for short and
`*02*02*A8<body><CHK>` for extended frames, with no `#` and no A3. bt_termo sends
`*04*03*<n>*01*$04…*01*$04…#`.

## 2. Addressing (WHERE)

| byte / bits | meaning | example |
|---|---|---|
| zone byte `< 0x80` | zone = decimal value | `28` → `40`; `00` → `#0` (central) for most dims |
| zone byte `≥ 0x80` in 9D/9E/B7 frames | `0x80\|zone` + low nibble N of the next byte → `zone#N` (actuator N) | `A8 31` → `40#1`, `80 33` → `0#3` |
| byte after zone = `3N` | high nibble 3 = system 4 (thermo). N = probe/actuator index | B4: `28 31` → WHERE `140` (N prefixed) |
| extended frames: `03 x4` after zone | low nibble 4 = system 4; `03 34`, `03 04`, `03 44` all decode the same | |
| `D2` = state/answer | `D1 … 03 02` = write (OWN `#DIM`) | |

## 3. Short frames: `A8 C0 ZZ 3N VV CHK A3`

| C0 | OWN produced | value rule |
|---|---|---|
| B4 | `*#4*Z*0*TTTT##` measured temperature | T = VV (tenths of °C, 0–25.5 °C) |
| B5 | `*#4*Z*0*TTTT##` | T = VV + 256 (25.6–51.1 °C) |
| 90 / 91 / 92 | `*#4*Z*#14*TTTT*M##` set point, M = 1 / 2 / 3 | T = VV × 5 (VV in half degrees). `2B` → `0215` |
| 93 | `*4*WHAT*Z##` (only VV `0D`→39, `0E`→40 as input) | see §5 for the command table |
| 96 | `*#4*Z*#20*S##` | lookup: `00`→1, `01`→0, `10`→2, `11`→3, `12`→4, `20`→5, `21`→6, `22`→7, `23`→8, `2F`→9, `30`→10, `31`→11, `32`→12 … |
| B7 | `*#4*Z*20*S##` | same lookup as 96 |
| 9D | `*4*4001#VV*Z##` | VV decimal |
| 9E | `*4*4002#VV*Z##` | VV decimal |
| 9F | `*4*41..44*Z##` | `E0`→41, `E1`→42, `E2`→43, `E5`→44 |
| 99, A6, A9, B3 | rejected as input (these are requests bt_termo *sends*, see §5) | |

## 4. Extended frames: `A8 D2 ZZ 03 34 DD B1 B2 B3 CHK A3`

DD selects the OWN dimension:

| DD | OWN | field rule (B1 B2 B3) |
|---|---|---|
| 01 | `*#4*Z*4*B1##` | B1 decimal |
| 02 | `*#4*Z*5*B1##` | B1 decimal |
| 03 | `*#4*Z*6*B1##` | B1 decimal |
| 04 | `*#4*Z*8#(B1+1)*TTTT##` | T = B2 × 5 |
| 05 | `*#4*Z*7*A*B*TTTT##` | T = B2 × 5. (A,B) come from a B1 lookup table: `F0`→1*1, `F1`→2*1, `F2`→1*2, `F3`→2*2, `F4`→0*2, `FF`→0*5, `10`→1*3, `11`→1*4, `12`→2*3, `13`→2*4, `14`→3*3, `15`→3*4, `16`→3*2, `17`→3*1, `18`→0*3, `19`→0*4, `1A`→0*1. Any other B1 gives a truncated/invalid output |
| 08 | `*#4*Z*60*B3##` | B3 decimal (humidity %) |
| 0B | `*#4*Z*11*B1##` | B1 decimal |
| 0C | `*#4*Z*2*TTTT##` | T = B1·256 + B2 (tenths) |
| 0D | `*#4*Z*13*X##` | B1 lookup: `00`→00, `0A`→01, `14`→02, `1E`→03, `80`→4, `81`→5, `86`→6, `82`→7, `85`→8, `F6`→11, `EC`→12, `E2`→13 |
| 0E | `*#4*Z*14*TTTT*3##` | T = B1·256 + B2. `*3` is a constant |
| 0F | `*#4*Z*3*TTTT##` | T = B1·256 + B2 |
| **12** | `*#4*Z*12*TTTT*3##` **+** `*4*MODE*Z##` | T = B2·256 + B3. `*3` is constant. MODE from B1: `F0`→1, `F1`→0, `F2`→102, `F3`→202, `FF`→303, `10`→108, `11`→107, `12`→208, `13`→207, `1B`→408, `1C`→407, `1D`→402, `1E`→410, `1F`→508, `20`→507, `21`→502, `22`→510; anything else gives `*4*-1*Z##` |
| 13 | `*#4*Z*19*a*b##` | a from B2 (`00`→1, `01`→0), b from B1 lookup (`00`→1, `01`→0, `10`→2, … `80`+n→100+n) |
| 14 | `*#4*Z*17*B1*B2*TTTT##` | T = B3 × 5 |
| 16 | `*#4*3#Z*22*B2*TTTT*lo*hi##` | T = B3 × 5. lo = low nibble of B1 (F = empty), hi = bit 4 inverted |
| 17 | `*#4*Z*21*B1*B2*B3##` | decimals |
| 19 | `*#4*Z*29*B1*B2*B3##` | decimals (B1 ≤ 0x7F) |
| 21 | `*#4*Z*15*lo*WWWW*bbbb##` | lo = B1 low nibble, W = B2·256 + B3, bbbb = B1 high nibble as 4 binary digits |

`D1 ZZ 03 02 DD …` gives the same rules with `#` before the dimension (`*#4*Z*#DIM*…`). The
firmware accepts DD = 01, 02, 04, 05, 0B, 0C, 0F, 14, 16, 17, 19 for D1.

The user's example: `A8 D2 28 03 34 12 F0 00 C8 E7 A3` → Z = 0x28 = 40, DD = 12,
B1 = F0 → mode 1, T = 0x00C8 = 200 → `*#4*40*12*0200*3##` + `*4*1*40##`.

## 5. OWN → SCS (what bt_termo puts on the bus)

| OWN | SCS body (wire adds A8 … CHK A3) |
|---|---|
| `*4*1*Z##` | `93 ZZ 30 00` |
| `*4*0*Z##` | `93 ZZ 30 01` |
| `*4*102*Z##` / `202` / `302` | `93 ZZ 30 02` / `03` / `04` |
| `*4*103*Z##`, `*4*203*Z##`, `*4*303*Z##` | `93 ZZ 30 0F` (all three map to the same OFF byte) |
| `*4*40*Z##` | `93 ZZ 30 0E` |
| `*4*41*Z##` / `42` | `9F ZZ 30 E0` / `E1` |
| `*#4*Z*#14*TTTT*M##` | `9(M-1) ZZ 30 T/5` (for example `0215`,1 → `90 28 30 2B`) |
| `*#4*#0*#14*TTTT*M##` | `D1 00 03 02 C1 MM TT 00` (MM: 1→12, 2→22, 3→02) |
| `*4*1*#0##`, `*4*102*#0##`, `*4*303*#0##` | `D1 00 03 02 C1 F0/17/06 00 00` |
| `*#4*Z##` (status request) | four frames: `99 ZZ 30 00`, `99 ZZ 30 12`, `99 ZZ 30 0E`, `99 ZZ 30 0D` |
| `*#4*Z*0##` / `*2` / `*11` / `*12` / `*13` / `*14` / `*19` | `99 ZZ 30 00` / `0C` / `0B` / `12` / `0D` / `0E` / `13` |
| `*#4*Z*30##` / `31` / `32` | `99 ZZ 30 C3` / `C4` / `C5` |
| `*#4*Z*20##` | `A9 ZZ 30 10` |
| `*#4*Z*4##`, `5`, `6`, `7`, `15`, `21`, `29`, `60`, `18` | `D1 ZZ 03 03 DD 00 00 00`, with DD = 01, 02, 03, 05, 21, 17, 19, 08, CD |
| `*#4*Z*#11*v##` | `D1 ZZ 03 02 0B v 00 00` |
| `*#4*Z*#5*v##` / `*#4*Z*#4*v##` | `D1 ZZ 03 02 02 v 00 00` / `D1 ZZ 03 02 01 v 00 00` |
| `*#4*Z*#7*1*1*TTTT##` | `D1 ZZ 03 02 05 F0 T/5 00` |
| `*#4*Z*#8#1*TTTT##` | `D1 ZZ 03 02 04 00 T/5 00` |
| `*#4*Z*#20*1##` | `A6 ZZ 30 00` |
| `*4*4002#V*0#N##` | `9E 80 3N V` |
| `*4*1*Z#1##` | `D1 (80\|Z) 13 02 C1 F0 00 00` |
| `*#4*Z#1*20*0##` | `99 (80\|Z) 31 10` |

Some inputs emitted nothing on this unconfigured device (for example `*4*4001#…`,
`*#4*Z*#2/#3…`, `*#4*Z*#17…`). `*#4*40*22##` crashes bt_termo.

## 6. Answers for the minsky translator

- **F0** is the mode byte (B1) of dim 12. It is a lookup table, not a flag. F0 gives heating
  (`*4*1`), F1 cooling (`*4*0`), F2 antifreeze (`102`), F3 thermal protection (`202`) and FF OFF (`303`).
  `1x/2x` values are the 107/108/2xx/4xx/5xx modes.
- **"1*1"** in `*#4*Z*7*1*1*T` comes from the same kind of lookup on B1 of dim 05 (table in §4).
  F0 always gives `1*1`.
- **"*3"** in dims 12 and 14 is a constant emitted by the firmware. It does not come from any frame byte.
- **Setpoint encodings differ.** Dim 05/04/14/16 use B × 5 (half-degree steps ×10). Dims
  0C/0E/0F/12 use a 16-bit value in tenths. Short 90–92 frames use VV × 5.
- **Area/general WHERE.** A zone byte of 0 gives `#0`, and bit 7 of the zone byte together with the
  low nibble of the `3N` byte gives `Z#N` (actuators).
- **Unknown frames.** `99`, `A6`, `A9` and `B3` are request/command frames that bt_termo
  sends, so they have no SCS→OWN translation. `96`/`B7` are `#20`/`20` status. `9D` is `4001`.
