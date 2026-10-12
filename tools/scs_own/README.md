# scs_own: SCS ⇄ OpenWebNet translator recovered from the BTicino MyHOMEServer1 firmware

Two implementations of the same rules, both validated against the firmware's own translators
(`bt_luci`, `coso`, `bt_termo`, `bt_supervisione`, `bt_device`, `bt_multi` from the MyHOMEServer1
image, run under ARM emulation on a fake SCS bus):

| Folder | What | Validation |
|---|---|---|
| `scs_own.c`, `scs_own.h`, `scs_own_tables.h` | C99 port, frame → OpenWebNet only, no allocation, no dependencies | identical to the Python on the 26,809-row corpus (`make test`); during development also on 150,000 random and 188,193 mutated frames |
| `py/` | Python translator, both directions (`scs_own_all.py` + rule modules + `fw_tables.json`) | reproduces 111,820 / 111,820 recorded firmware answers (`python3 py/validate_all.py`) |
| `hex2own_corpus.tsv` | every frame the firmware decodes, with its OpenWebNet output | the test oracle for both ports |
| `corpus/` | the 31 recorded firmware sweeps (hex → OWN and OWN → hex, per program) that `validate_all.py` replays | 111,820 answers |

The byte-level rules are written up in `py/SCS_OWN_ALL_MAP.md` (all WHO) and `py/SCS_OWN_MAP.md`
(heating in detail). Nothing in them comes from manuals: every row is observed firmware output.

## C port

```sh
make            # builds scs_own_test
make test       # replays hex2own_corpus.tsv: prints 26809/26809
echo 'A8 B8 31 12 00 9B A3' | ./scs_own_test -
```

API (see `scs_own.h`):

```c
#include "scs_own.h"
uint8_t body[8];
int n = scs_parse_hex("A8 B8 31 12 00 9B A3", body);   /* 4 or 8 body bytes, 0 = not a frame */
char out[SCS_OWN_MAX][SCS_OWN_LEN];
int k = scs_to_own(body, n, out);                     /* k messages, out[0] = "*1*1*31##" */
```

`scs_own_tables.h` is generated from `py/fw_tables.json` by `gen_c_tables.py`; regenerate it if the
JSON changes. The port is plain C99 and is meant for the host side (or an ESP8266 / ESP32 companion);
it does not fit the PIC18F26K80 (the tables alone are larger than its flash).

## Python translator

```sh
python3 py/scs_own_all.py hex 'A8 B8 31 12 00 9B A3'      # -> *1*1*31##
python3 py/scs_own_all.py own '*#4*40*14##'               # -> A8 99 28 30 0E 8F A3
python3 py/validate_all.py                                # replays corpus/: TOTAL 111820/111820
```

`../scsgate_own.py` wraps it for the gateway's serial output.

## Coverage

WHO 0 scenarios, 1 lights and dimmers (all dimensions), 2 covers (incl. position frames), 4 heating
(all short and extended frames), 9 auxiliaries, 13 gateway clock, 14 lock, 15 CEN, 18 energy, 22 sound,
25 CEN+ / dry contacts, 1004 / 1013 diagnostics. The firmware translates nothing for WHO 3, 5, 6, 7, 16, 17.
