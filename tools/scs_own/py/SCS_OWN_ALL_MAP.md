# SCS ⇄ OpenWebNet map for lights, covers, sensors, thermo and energy (mhs1 firmware)

Everything here is observed output of the mhs1 firmware's own translators, run under ARM
emulation on a fake SCS bus and fed with tens of thousands of test frames and commands:

| WHO | translator (mhs1) | scsserver client id | OWN port |
|---|---|---|---|
| 1 lighting, 0/14 (bt_luci extras) | `home/bticino/bin/bt_luci` | 01 | 30001 |
| 2 automation (covers) | `home/bticino/bin/coso` + `libcoso/libplug_automation_*` | 45 | 30002 |
| 9 auxiliaries | `coso` + `libplug_aux_*` | 45 | 30002 |
| 4 thermoregulation | `home/bticino/bin/bt_termo` (see SCS_OWN_MAP.md) | 04 | 30004 |
| 18 energy | `home/bticino/bin/bt_supervisione` | 18 | 30018 |

The standalone translator is `scs_own_all.py` + `fw_tables.json` (+ `thermo_own.py`, `energy_own.py`,
`cen_own.py`, `device_own.py`, `sound_own.py`, `fw_quirks.py` and `scs_own_fw.py` for WHO 4). `validate_all.py` replays every
sweep result through it.

## 1. Wire format and scsserver client protocol

```
A8 <body> <XOR of body> A3      body = 4 bytes (short) or 8 bytes (extended)
```
Inside the gateway, scsserver hands frames to bt_luci/coso/bt_supervisione as
`*02*01*$17<body>#` (short) / `*02*02*$18<body>#` (extended); bt_termo gets `*02*01*A8<body><chk>`.
Apps send frames back as `*<id>*03*01*01*$04<body>#` (short, "$03" for point commands) and
`*<id>*03*01*02*$06<body>#` (extended).

## 2. Addressing for WHO 1 / 2 / 9 (short frames)

Short frame: `[dest] [source] [type] [value]`.

| frame | meaning | OWN WHERE |
|---|---|---|
| `aa ss 12 vv` | point command to address `aa` (source `ss` ignored) | `A PL` from the two nibbles: `%X%X` when both < 10, else `%02d%02d` (`0F`→`0015`, `A5`→`1005`, `F1`→`1501`) |
| `B8 aa 12 vv` | status broadcast from address `aa` | same rule on `aa` |
| `B1 00 12 vv` | general command | `0` |
| `B3 0A 12 vv` | area A command | `A` |
| `B5 0N 12 vv` | group N command | `#N` |
| `EC ii 00 00 aa ss 12 vv` | same, through bus interface `ii` | `WHERE#4#ii` |
| `aa ss 15 00` | status request | `*#1*WHERE##` / `*#2*WHERE##` |

## 3. WHO 1 value byte (type `12`)

Point/interface commands are reported as `*1*1000#WHAT*WHERE##` (echo of a command), status
broadcasts as `*1*WHAT*WHERE##`, general/area/group commands as `*1*WHAT*0|A|#N##`.
WHAT from the value byte (the `x` nibble is ignored where shown):

| value | WHAT | value | WHAT |
|---|---|---|---|
| `x0` | 1 (ON) | `x1` | 0 (OFF) |
| `x3` | 30 | `x4` | 31 |
| `1D 2D … 9D` | 2 … 10 (dimmer 20…100 %) | `AD BD CD DD ED FD` | 1000#11…16 |
| `16 26 … 86` | 11 … 18 | `96` / `A6` | 1000#50#9 / 1000#50#10 |
| `0B` | 20 | `1B 2B … 9B` | 21 … 29 |
| `AB` | 30 | `BB` | 31 |
| `CB DB EB FB` | 32 33 34 35 | `0D` | 1 |
| `0E` | 19 | `02–07, 0C, 0F` | 255 (status only) |

OWN → SCS uses the inverse table (`*1*WHAT*W##` → `aa 00 12 vv`). `*1*19*W##` makes the firmware
emit a truncated 3-byte body (`aa 00 12`), reproduced as-is.
Dimmer step `*1*1#N*W##` → `D1 aa 01 42 0D 00 00 N`.

Other type bytes bt_luci decodes from address 31: `10`→`*14*1*W##`, `11`→`*14*0*W##`,
`17`→`*0*0*W##`, `1C`→`*0*42*W##`, `1D`→`*1*34*W##`.

## 4. WHO 2 covers (coso)

| value | status `B8 aa 12 vv` | command `aa ss 12 vv` |
|---|---|---|
| `08` | `*2*1*W##` (UP) | `*2*1000#1*W##` |
| `09` | `*2*2*W##` (DOWN) | `*2*1000#2*W##` |
| `0A` | `*2*0*W##` (STOP) | `*2*1000#0*W##` |

OWN → SCS: `*2*0*W##` → `0A`; `*2*1*W##` → `0A` then `08`; `*2*2*W##` → `0A` then `09`
(coso always sends STOP first). `*#2*W##` → `aa 00 15 00`.
Cover dimensions: `*#2*W*10##` → `D1 aa 01 43 09 00 00 00`; `*#2*W*#11*v##` → `D1 aa 01 42 09 39 v 00`;
`*#2*W*#12*1##` → `… 42 09 39 6F 00`; general (`0`) uses `D2 00 01 33/32 09 …`.

## 5. WHO 9 auxiliaries (coso)

`B8 aa 9A|9B vv` → `*9*WHAT*AUX##` with AUX = high nibble of `vv` (0…15) and WHAT from the
type byte and the low nibble of `vv`: `9A`: `0`→0, `4`→1, `8`→2, `C`→9; `9B`: `0`→3, `4`→4,
`8`→5, `C`→10. Other low nibbles and other `9x` bytes give nothing. The point-command form
(`aa ss 9A vv`) is not decoded, and coso emits no SCS frame for `*9*WHAT*AUX##` commands
(0 of 42 tried). Full observed table: `fw_tables.json["AUX"]`.

## 6. WHO 1 dimensions (extended frames, bt_luci)

Layout `D1|D2|D5  aa  01|11  4x  DIM  b1 b2 b3`:
`43` = request (OWN `*#1*W*DIM##`), `42` = write (`*#1*W*#DIM*…##`), `44` = state answer
(`*#1*W*DIM*…##`); `D1 aa 01` point, `D5 0A 11` area, `D5 0N 01` group, `D2 00 01` general;
high nibble of byte 3 = bus interface.

| DIM byte | OWN dimension | data |
|---|---|---|
| `0D 0D` | 1 (level+speed) | `L-100`, speed |
| `06` | 2 (temporisation) | h m s |
| `0D 00` | 4 | |
| `15` | 5 | b3 (24-bit with b1 b2) |
| `10` | 6 | 24-bit |
| `16` | 7 | h m s |
| `17` | 8 | 24-bit |
| `0C` | 12 | h m s |
| `0B` | 14 | 16-bit |
| `07` | 15 | flag |
| `09` | 10/11/12 (covers) | |

`*#1*0*3##` is special: short frame `B1 00 1B 00`.

## 7. WHO 4 thermoregulation

SCS → OWN: SCS_OWN_MAP.md (bt_termo). OWN → SCS for every dimension (`thermo_own.py`), rebuilt from the
differential runs dl4/dl4b/dl4c/dl4d (8,700 command variants against bt_termo).

**Address model** (bt_termo splits WHERE on `#`):

| WHERE | kind | addr | ext header | short byte | prefix |
|---|---|---|---|---|---|
| `1`..`99`, zero-padded `01` | zone | Z | `03` | `30` | `D1` |
| `0` | zone 0 (all zones) | 00 | `03` | `30` | `D2` (broadcast); `00`/`000` or any `#` suffix → `D1` |
| `#0` / `#0#N` | central / central probe N (≤255) | 00 / N | `03` | `30` | `D1` |
| `#N` (≤255) | group | 00 | `03` | `30` | `D1` (N only in the `C2` group forms) |
| `NZZ` N=1..9 | probe | ZZ | `N3` | `3N` | `D1` (`0ZZ` = zone ZZ) |
| `Z#N` Z≤127 N=1..15 | actuator | `80\|Z` | `N3` | `3N` | `D1`; `Z#0` → `D5 Z 03` (only WHAT 0/1) |
| `X#4#NN`, any `a#b#c…` | interface | as `X` | | | dims 0, 11-13, 19, 27, 28 and writes #0/#3/#4/#5/#7/#8/#11/#14 are refused; dim 22 → zone b actuator c |

**Requests** `*#4*W*DIM##` (state forms `*#4*W*DIM*values##` of dims 0,12,13,15,19,20 are taken as the request):

| DIM | accepted for | frame |
|---|---|---|
| 2,3,14,30,31,32 | every kind | `99 addr short 0C\|0F\|0E\|C3\|C4\|C5` |
| 0 | zone `99 Z 30 00`; `0`,`00`,`01`.. → 8 frames `99 Z 31..38 00`; `#0`, `#N`, probe | never `#0#N`, actuator, interface |
| 11,12,13,19,27,28 | real zones only | `99 Z 30 0B\|12\|0D\|13\|F1\|F2` |
| 16 / 17 | probe & actuator / actuator with Z≥1 | `99 addr short 90\|14` |
| 20 | zone, `#0#N` → `A9`; `0`, `#0`, `#N` → `B9 00`; actuator → `99 .. 10`; never probe | |
| 15 | zone, zone 0, probe, actuator | `D1\|D2 addr hdr 03 21` |
| 18,21,29,60 | all (21/29 never for probes or zone-0 actuators) | `.. 03 CD\|17\|19\|08` |
| 4,5,6,7 | real zones only | `D1 Z 03 03 01\|02\|03\|05` |
| 22 | only `a#b#c` | `D1 80\|b c3 03 16` |
| none | zone → 4 frames (`00 12 0E 0D`); `#0`/`#0#N` → `99 N 30 C0`; `#N` → `D1 00 03 03 C2 N` | |

**Writes** `*#4*W*#DIM*..##` (T = temperature ×0.1 °C, checked as T/5):

| DIM | rule |
|---|---|
| #20 s | s 0..22 → status byte (STAT table), 100.. → `(0x80+s-100)&FF`; `A6` zone/`#0#N`, `B6` zone 0/`#0`/`#N`, `96` probe/actuator |
| #21 a b c / #29 | `17\|19 a b c`; #21: a≤3 b≤3 c≤100; #29: a≤100 b≤3 c≤100; all kinds |
| #31 h m / #32 | `C4\|C5 h m 00`; h≤23 (#31) or ≤24 (#32), m≤59, extra fields ignored; all kinds |
| #18 a b | `CD a b 00`; a≤9, b≤255; all kinds |
| #17 a b T | probe & actuator only; `14 a b T/5` (a,b ≤255) |
| #14 TTTT M | T/5 in 6..80; zone `8F+M Z 30 T/5` (any digit count); `#0`/`#0#N` `C1 12\|22\|02 T/5` and `#N` `C2 N code T/5` need 4 digits |
| #0 v / #3 v | zone only; v≤511 → `F0 hi lo`; 30≤v≤200 → `0F hi lo` |
| #4 #5 #11 v | zone only, v≤3 |
| #7 m p [T] | zone only; pairs 1\*1→F0, 0\*1→1A, 2\*1→F1, 3\*1→17 need T (6..80 → T/5); other pairs (table `ENC7`) → byte 2 `FF`; pairs coded 00 (0\*0, 3\*5, 1\*5, 2\*5, 2\*31, 2\*32, 3\*31, 3\*32) give byte 2 `00` or `0C` at random |
| #8#N TTTT | zone only, N=1..8, `04 N-1 T/5`; T/5 windows: 1: 28-80, 2: 6-69, 3: 20-40, 4: 50-70, 5/6: 6-79, 7: 20-80, 8: 9-80 |

**Commands** `*4*WHAT*W##`: WHAT 0/1 → zone `93 Z 30 01\|00`, every other kind `pfx addr hdr 02 C1 F1\|F0 00 00`;
zone-only WHATs 39/40/41/42/45/102/103/202/203/302/303 (`93`/`9F`); central `#0`/`#0#N` codes `C1`
(0/1/102/103/115[#11xx]/202/203/215/302/303/315/3000, 11xx→`11`, 12xx→`13`, 21xx→`21`, 22xx→`23`,
31xx→`01`, 32xx→`03`, with xx00 → byte 00 for 11/12/21/22 and FF for 31/32) and `C2 00 10\|20\|00` for
111/211/311; groups `#N`: 102/103/202/203/302/303 → `C2 N 17\|16\|27\|26\|07\|06`, 111/211/311 → `C2 N 10\|20\|00`,
everything else refused; 4001/4002[#V] → `9D\|9E addr short V` (V≠0 only for actuators of zone 0).

## 8. WHO 18 energy (bt_supervisione)

WHERE `5N` → address `A0|N`; WHERE `1` → `00`. Requests `*#18*W*DIM##` → `D1 aa 02 33 hi lo 00 00`:

| DIM | hi lo | DIM | hi lo |
|---|---|---|---|
| 51 | 50 15 | 53 | 50 17 |
| 54 | 50 18 | 71 | 70 03 |
| 72 | 70 04 | 73 | 70 05 |
| 113 | 00 1D | 120 | 00 24 |
| 510#N / 512#N / 513#N / 514#N | 50 14|1B|1C|1D N | `*#18*W*#1200#1*0*0*1*1##` | `D1 aa 02 32 00 02 1D 00` |

Commands `*18*WHAT*W##`: 53…59 → `D1 aa 02 33 50 11…14,1A,1B,1C 00 00` (`57#N` etc. put N in b7);
71…75 → `D1 aa 02 32 70 01|01|02 FF|02|04 00`.

Answers from the bus are type-`34` frames only: `D2 aa 02 34 hi lo v1 v2`, V = 16-bit `v1 v2`
(`01 F4` = 500). Address `A1`→ WHERE `51` (meters `5N` ↔ `A0|N`); address `00` → WHERE `10`.

| hi lo | OWN | note |
|---|---|---|
| `00 11`…`00 19` | `*#18*5N*11…19*V##` | dimension = "1" + (lo − 0x10) |
| `00 1A`…`00 29` (not 1E, 24) | `*#18*5N*110…125*V##` | same rule, e.g. `1D`→113, `1F`→115 |
| `50 01` | `*18*51#1*5N##` | |
| `50 04` / `50 05` | `*#18*5N*515*1*0*0##` / `*#18*5N*516*0*0*1*0##` | |
| `50 06` / `50 07` | `*#18*5N*517#1*V##` / `*#18*5N*517#2*V##` | |
| `50 15` / `50 17` / `50 18` | `*18*51#V*5N##` / `*18*53#V*5N##` / `*18*54#V*5N##` | |
| `50 16` / `50 19` | `*18*52#1#v2#V*5N##` / `*18*55#v2#V*5N##` | |
| `70 02` / `70 03` / `70 05` | `*18*73#3#52*749#-5##` / `*#18*749#-5*71*0*0*0*0*0*0##` / `*#18*749#-5*73*1##` | firmware prints a garbled WHERE for actuators |

Other header nibbles (`30`, `31`, `32`, `33`, `35`…) are classified but never translated.
Full observed table (72 rows, 6,144 frames tried): `fw_tables.json["ENERGY"]`.


## 10. Additions from the MyHOME / OWNd catalog sweep

Every dimension and command that `OWNd` (2.0.0b8) and the MyHOME golden corpus define for the
WHOs the mhs1 firmware handles was fed to the firmware (2,947 new commands). Results:

### WHO 1 (bt_luci)
| OWN | SCS | note |
|---|---|---|
| `*#1*W*#5*v##` / `*#1*W*#6*v##` (v ≤ 100) | `D1 aa 01 42 15|10 00 00 v` | PIR sensitivity / illuminance |
| `*#1*W*#7*h*m*s##` | `D1 aa 01 42 16 h m s` | motion timeout |
| `*#1*W*#8*0##` | `D1 aa 01 42 17 00 00 00` | |
| `*#1*W*#12*h*s*v##` (h ≤ 359) | `D1 aa 01 42 0C (h&0xFF) s v` | HSV colour; the hue loses its high bit |
| `*#1*W*12*h*s*v##` (state) | `D1 aa 01 44 0C …` | states are accepted only for dims 12 and 14 (points) and 15 (groups) |
| `*#1*W*#14*m##` (m ≥ 1) | `D1 aa 01 42 0B hi lo 00` | colour temperature in mireds |
| `*#1*#G*15##`, `*#1*#G*#15*v##` | `D5 0G 01 43|42 07 00 00 (1-v)` | groups only |
| `*1*1#N*W##` / `*1*0#N*W##` | `D1 aa 01 42 0D 00|01 00 N` | dimmer step up/down, also `0` (D2 00 01) and `#G` (D5 0G 01) |
| `*1*WHAT*00##`, `*1*WHAT*100##` | `B3 00 12 v`, `B3 0A 12 v` | area 0 / area 10 |
| `W#4#ii` | header byte 3 = `ii<<4 | 1` (`25#4#02` → `D1 25 21 …`) | bus interface |

Rejected by the firmware: `*#1*W*#4*…##`, `*#1*W*#13*…##`, `*1*34*W##`, `*1*999*W##`, all
`*1*1000#…*W##` echo forms, WHO 0 / 14 / 1001 commands, and `*#1*W*#1*100*s##` (level must be 101–200).


### WHO 1 timers, scenario recall and WHO 0 (bt_luci templates)
| OWN | SCS |
|---|---|
| `*1*30#h#m*W##` (h 1–23, m 0–59) | `D1|D2|D5 … 42 0D 03 h m` (same header rule as other dimension writes; interface nibble allowed) |
| `*1*31#h#m*W##` | `… 42 0D 04 h m` |
| `*1*50#9*W##`, `*1*50#10*W##` | value byte `96`, `A6` (point/general/area/group forms) |
| `*0*S*W##` (S 0–31) | `aa 00 14 S`, sent twice by bt_luci; `0`→`00`, area `A`/group `#A`→`0A`, 2-digit `AP`→`aa`, `#4#ii`→`EC ii 00 00` prefix |
| `*0*44*W##` | `aa 00 1C E0` |
bt_luci drops every second WHO 0 command while the previous 2-frame transaction is still running,
so consecutive scenario commands need a pause.

### WHO 2 (coso), corrected by the differential test
coso accepts point addresses (2- or 4-digit, leading zeros allowed), general `0`, areas `A`, groups
`#N` and interface routing `W#4#ii`, but only once it has seen the device on the bus (it learns
addresses from status frames; in a fresh emulator nothing is accepted until a frame arrives).

| OWN | SCS |
|---|---|
| `*2*0|1|2*W##` | `0A` / `0A`+`08` / `0A`+`09` with the WHO 1 address rules (`EC ii 00 00` prefix for `#4#ii`) |
| `*2*10*W##` | `D1 aa 01 42 09 09 00 00` (point / area `D5 0A 11`), `D2 00 01 32 …` (general), `D5 0N 01 32 …` (group) |
| `*#2*W##` | `aa 00 15 00` (same address forms) |
| `*#2*W*10##` | `… 43 09 00 00 00` (points, areas) / `… 33 09 …` (general, groups) |
| `*#2*W*#11*v##`, `*#2*W*#11#001*v##` (v ≤ 100) | `… 42|32 09 39 v 00` |
| `*#2*W*#12*1##` | `… 42|32 09 39 6F 00` |
Interface routing on dimension frames sets the high nibble of byte 3 (`31#4#01` → `D1 31 11 …`).
Rejected: WHAT 3/4/11/12/1000#x, `#1` position, `#10`, dimensions 0/1.

### WHO 9 aux commands (coso)
`*9*WHAT*AUX##` (AUX 0–15) → `B0 00 9A|9B|9C (AUX<<4)|code`: WHAT 0/1/2/9 → `9A` code 0/4/8/C,
3/4/5/10 → `9B` code 0/4/8/C, 6/7/8 → `9C` code 1/2/4. `*#9*AUX##` is rejected.

### WHO 4 (bt_termo), new forms
| OWN | SCS |
|---|---|
| `*4*WHAT*#0##` central programs | `D1 00 03 02 C1 code b2 00`: 0→F1, 1→F0, 102→17, 103→16, 115→14, 202→27, 203→26, 215→24, 302→07, 303→06, 315→04, 3000→05, 11NN→11 (NN-1), 12NN→13 (NN-1), 21NN→21 (NN-1), 22NN→23 (NN-1), 31NN→01 (NN-1, 3100→FF), 115#11NN→14 (NN-1) |
| `*4*111|211|311*#0##` | `D1 00 03 02 C2 00 10|20|00 00`; `*4*311*#N##` → `C2 N 00` |
| `*4*WHAT*#N##` (group) | `D1 00 03 02 C2 N code b2` |
| `*4*0|1*0##` | `D2 00 03 02 C1 F1|F0 00 00` |
| `*4*4001|4002[#V]*W##` | `9D|9E addr 3n V` (zone, probe `NZZ`, actuator `Z#N` → `0x80|Z`, central `#0`) |
| `*#4*#0#N##`, `*#4*#0#N*#14*T*M##` | `99 N 30 C0`, `D1 N 03 02 C1 M T/5 00` |
| `*#4*#N*#14*T*M##` | `D1 00 03 02 C2 N M T/5` |
| `*#4*Z#N*#20*v##`, `*#4*Z#N*17##` | `96 (80|Z) 3N code`, `99 (80|Z) 3N 14` |
| `*#4*0Z*0*T##` (zero-padded zone, state form) | eight probe requests `99 Z 31…38 00` |
| state forms `*#4*Z*0|12|13|19|20*…##` | treated as the plain request |
| `W#4#ii` | the interface is ignored |

### WHO 18 (bt_supervisione), new forms
| OWN | SCS |
|---|---|
| `*#18*W*11##` | `D1 aa 02 33 00 11 00 00` |
| `*#18*W*511#m#d##`, `*#18*W*52#yy#mm##` | `D1 aa 02 33 50 1A m d`, `… 50 16 yy mm` |
| `*#18*W*513#m##`, `*#18*W*514#m##`, `*#18*W*510#N##`, `*#18*W*512#N##` | `… 50 1C|1D|14|1B m 00` |
| `*#18*W*#1200#1*dur##` | `D1 aa 02 32 00 02 1D dur` |
| `*18*59#m*W##`, `*18*510#m*W##` | `… 33 50 1C|1D m 00` |
| `*18*51*W##` | `D1 aa 02 32 50 01 00 00` |
| WHERE | `1`→00, `1Y`→0Y, `3Y`→8Y, `5Y`→AY, `7Y#0`→BY with header byte 3 = `12`; `7`, `71`, `#0` rejected |
State forms (`*#18*W*DIM*values##`) are sent as the plain request; 1, 999, 1200, 60, 70, 77 are rejected.

### WHO 0 / 14 frames decoded by bt_luci
`B8 aa 10 00`→`*14*1*W##`, `B8 aa 11 00`→`*14*0*W##`, `B8 aa 17 v`→`*0*v*W##` (v < 128),
`B8 aa 1C v`→`*0*42*W##` (v < 128), `*0*43*W##` (FF), `*0*41*W##`+`*0*44*W##` (80),
`B8 aa 1D 00|01`→`*1*34|39*W##`. The point-command form (`aa 00 10|11 00`) decodes the same.

## 11. CEN (WHO 15) and CEN+ (WHO 25), bt_luci

| OWN | SCS |
|---|---|
| `*15*BB*W##` (BB two digits, or ≥ 10) | `CD aa 14 BB` (type 03 for points, 04 for `0`/area) |
| `*15*BB#x*W##` (x = 1 short release, 2 extended, 3 release after extended; BB < 32) | `CD aa 10 (BB | x<<5)` |
| `*25*21…28#N*2ADDR##` (ADDR 0–2047) | `B2 lo (0x90+WHAT-21) (N | hi<<5)` with lo/hi = ADDR & 0xFF / ADDR >> 8 |
| `*25*11#N*1ADDR##`, `*25*12*1ADDR##`, `*25*13|14#a#b*1ADDR##`, `*25*15*1ADDR##` | `B1 ADDR 93 N`, `B1 ADDR 94 00`, `B1 ADDR 95|96 b`, `B1 ADDR 97 00` |
| `*25*31|32#1*3XX##` (XX ≤ 99) | `B4 0xXX 92 00|01` (XX taken as hex digits) |
| `*#25*3XX##` | `B4 00 90 0xXX` |
CEN WHERE forms: 2-digit `AP`, 4-digit with A ≥ 10, `0` general, `A` area; groups and `*#15*` requests are rejected.

SCS → OWN for CEN / CEN+ frames (bt_luci):

| frame | OWN |
|---|---|
| `CD aa 14 BB` | `*15*BB*W##` (BB as two decimal digits, W from `aa` like lights) |
| `CD aa 10 vv` | `*15*(vv&0x1F)#(vv>>5)*W##` |
| `CD aa 11 vv` | `*15*(vv&0x1F)#3*W##` |
| `B2 lo 9t N` (t = 0…7) | `*25*(21+t)#(N&0x1F)*2ADDR##`, ADDR = lo + (N>>5)·256 |
| `B1 lo 93 N` / `94` / `95 N` / `96 N` / `97` | `*25*11#N*1lo##` / `*25*12*1lo##` / `*25*13#N#1*1lo##` / `*25*14#N#1*1lo##` / `*25*15*1lo##` |
| `B4 aa 90 vv` | `*#25*3vv##` |
| `B4 aa 91|92 vv` (vv 0/1) | `*25*(31+vv)#0|1*3<aa as hex digits>##` |
| `B1 aa 10 00`, `B3 aa 10 00`, `B8 aa 10 00` | `*14*1*0##`, `*14*1*<aa decimal>##`, `*14*1*W##` |
Sweep: 9,200 frame types; full table in `fw_tables.json["CEN"]`.

## 12. WHO 1004 / 1013 diagnostics and WHO 13 gateway (bt_device)

| OWN | SCS |
|---|---|
| `*#1004*W*D##`, D = 1…8, 10, 11, 12 | `D1 aa b2 33 code 00 00 00`, code = 80…87, 8E, 89, 8A |
| `*#1004*W*0##` | `D1 aa b2 32 8C 00 01 00` |
| `*#1004*W*20##` / `*#1004*W*23##` | `D1 aa b2 03 8F 00 FF|64 00` |
| `*#1004*W*13##` | `D0 00 03 F3 00 00 00 00` (address independent) |
| `*#1013**6|8|10|11##` | `D2 00 0F 03 85|87|8E|89 00 00 00` |
| `*1013*1*0##` | `D2 00 0F 02 8C 00 00 00` |
WHERE for WHO 1004 is the decimal device number 0–4095: `aa` = low byte, high nibble of `b2` = bits 8–11
(`311` → `37`, `13`); `0` uses header `D2 00 03`; `#N` uses `D1 00 03`; `#4#ii` is ignored.
`*#13**N##` (time, date, version, IP, MAC, uptime, …) is answered by bt_device itself and never
reaches the bus, as are the WHO 13 writes.

## 13. WHO 22 sound diffusion (bt_multi)

bt_multi (client id 22, OWN port 30022) translates WHO 22 only; every WHO 16 command is rejected
("Where field not recognized"). WHERE is `Z#S` or `Z#S#L` (zone, source, level):

| WHERE | short frame bytes 1–2 | extended header |
|---|---|---|
| `1#S` | `00 8F` | `D1 00 F8` |
| `2#S` | `S 8F` | `D1 S F8` |
| `2#S#L` | `E0|L 00 00 00` prefix + `S 8F` | `D3 S F8`, type nibble = L |
| `3#S#L` | `L 80|S` | `D1 L (S<<4)|8` |
| `5#S#L` | `L 8F`, type high nibble `B` instead of `9` | `D2 L F8` |

| OWN | frame (type byte low nibble, value) |
|---|---|
| `*22*3|4|5|6|9|10|11|12|13*W##` | `x4`, value `01|11|A0|B0|C1|D1|C1|D1|E0` (WHAT 3/4 low nibble = level, 0 for zone 1) |
| `*22*14#0*W##`, `*22*17#1*W##` | `x4 E1`, `x4 E4` |
| `*22*1#1|1#2*W##` | `x0 F0|F1` (zone 3: `(S<<4)|N-1`) |
| `*22*0|1|2|23#4#N*W##` | `x1|90|x2|xA`, value `(N<<4)|3` |
| `*22*31|32*W##` | ext `..35 01 41|42 04 00` |
| `*22*36#1*W##` | ext `..32 07 C0 C0 41` |
| `*#22*W*1|5|6|11|12##` | `x5 00|A0|C0|A0|8F` |
| `*#22*W*2|4|17|18|19|20|25##` | ext `..33 07|07|08|0C|0C|0C|0F 00 00 00` |
| `*#22*W*#1*v##` (v ≤ 31) | `x3 v` |
| `*#22*W*#2*v##`, `*#22*W*#5*1##` | ext `..32 07 v C0 C0`, `..32 02 0F 00 00` |
| `*#22*W*#6*f##` | `x3 D1` + two frequency bytes (kept as recorded) |
| state forms `*#22*W*1|6|12*…##` | `x6 …`; `*#22*W*2|4|5|10|11|17…20*…##` → ext `..34 …` (see fw_tables / sound_own.py) |

## 14. Not translatable by the mhs1 firmware

No mhs1 program converts these WHOs to SCS, so the translator rejects them by design: WHO 3 (legacy
load control), 5 (burglar alarm), 6/7 (door/video entry), 16 (sound distribution, bt_multi ignores
it), 17 (scenario programmer), 24, 1001/1000/1004 group forms that bt_luci/coso reject, and the WHO
13 gateway dimensions, which bt_device answers locally.

## 15. Differential test against the original binaries

`gen_diff.py` generated 16k OWN command variants (every WHAT/dimension × address form × value edge), the
firmware answered them on the fake bus (dl1 bt_luci, dl2/aux2 coso, dl4* bt_termo, dl18 bt_supervisione),
and `diff_check.py` compared each answer with the translator. Random frames were also pushed onto the bus
(fz1 bt_luci 3,991, fz2 coso 2,946, multif bt_multi 6,783) and `check_fuzz.py` compared the decodes.
Everything found was folded into the rules above; what the firmware does that a stateless translator
cannot reproduce is listed in `fw_quirks.py` and skipped by the checkers:

* bt_termo `#7` pairs coded 00 emit byte 2 = `00` or `0C` depending on internal state.
* bt_termo actuator zone ≥128 / actuator ≥16 / 4-digit WHERE / `#0#N`, `#N` > 255 overflow into the
  neighbouring byte (`*4*1*128#1##` → `D1 00 23 …`).
* bt_supervisione `*#18*W*#1200#1*256##` emits a malformed 17-digit body.
* coso only decodes the advanced cover frames (`… 42|32|44 09 xx v y`, WHAT 10-14, dims #11/#13, status
  `*#2*W*10*…`) for devices it has already learned from bus traffic; the translator decodes them for any
  device (40 of the 2,946 fuzz frames differ only for that reason). One frame (`D2 01 21 32 09 39 77 08`)
  decodes as `#12` with value 9 and is left unexplained.
* bt_luci header quirks that are reproduced: `B1 aa` general with any aa, `B2 aa 12` → point `00`,
  `B4 aa 12` → point `0153`, `CD aa 12` → point aa, `B3 00` → area `00`; scenario status `B8 aa 1C v`
  uses bits 7-5 (0/1 → 42, 2 → 40, 3 → 41, 4 → 40|41 + 44, 5 → 46, 6 → 45, FF → 43) and bits 4-0 as `#N`;
  scenario events `B8 aa 17 v` with v in 0x80..0xBF are dropped; CEN `CD aa 11 v` → `*15*N#x` with
  x = (v>>5)+3; CEN+ zone 3 `B4 aa 90 v` prints `%X` below 0x9A and v-54 above.
* WHO 1 dimension frames `D1|D2|D5 aa bb 32|34|42|44 code v1 v2 v3` are decoded generically (code 06→2,
  0C→12, 10→6, 15→5, 16→7, 17→8; dims 2/7/12 three bytes, 5/6 20-bit, 8 24-bit; dim 12 status keeps a
  9th bit in byte 2's MSB; dim 5 has no status form; D5 needs header 01/11/21).
* WHO 9 aux frames are read from bytes 3-4 only; byte 1 must be B0/B1/B3/B5/B8 and byte 2 is ignored.

## 16. Live additions (scsmonitor on the real bus)

* Dimmer level status `D1|D2 aa 01 34 0D 0D lv sp` -> `*#1*W*1*(100+lv)*sp##`, `lv=sp=0` -> `*1*0*W##` (bt_luci).
* bt_device clock broadcasts: `D2 aa 09 x6 hh mm ss tz` -> `*#13**#0*hh*mm*ss*TZ##` and `D2 aa 09 x7 dd wm yy yy` ->
  `*#13**#1*W*DD*MM*YYYY##`; bytes are read as text (decimal prefix of the hex digits), TZ = bit 4 + low nibble of tz
  (low nibble F -> empty), W = high nibble of wm (F -> 0), MM = low nibble; day `0x28` is dropped by the firmware.
* Requests the gateway itself puts on the bus are not translated by the firmware when read back; `gw_inverse.py`
  reports them from generic rules (WHO 1/2 `aa 00 15 00`, WHO 1 dimension requests `43 code`, WHO 4 `99 z 3n code`
  and `D1 z n3 03 code`) plus the exact inverse table `INV` (2,382 bodies) built from the own->hex sweeps.
  `scs_to_own(frame, gateway=False)` disables this fallback (used by the validators).

## 9. Validation

`python3 validate_all.py` replays every sweep and differential file (111,783 rows, all passing);
`python3 diff_check.py dlX.tsv` and `python3 check_fuzz.py fzX_log.tsv WHOs` rerun the differential
comparisons. Frames the firmware never saw may still differ.
