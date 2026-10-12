# PIC_scsgate 544: state of the work, rules followed, how to resume

Written 2026-10-12 at the end of the session that built and flashed firmware 544. Project memory is off,
so this file (and its copies named below) is the memory: read it first when resuming. Nothing in it comes
from a manual; every fact was checked on the firmware record, the source or the board, and the place of the
evidence is named each time.

The same notes exist in three places:

* the user's fork, `docs/WORKLOG.md` (this file; branch `usb-flash-tool`, pull request #2);
* the project folder, `PIC_scsgate_RESUME_2026-10-12.md`, next to `PIC_scsgate_2026-10-12.bundle`
  (a git bundle of the fork's `master` and `usb-flash-tool`, complete history);
* the Mac, `~/Desktop/test1/SCSGATE_SESSION_NOTES.md`, written by the session that ran on the Mac
  (board facts, toolchain assembly, build and flash record).

## 1. Where everything is

| What | Where | State |
|---|---|---|
| Upstream | https://github.com/papergion/PIC_scsgate (Guido Pagani), `master` = `e4e2695` "V 543 - COMPLETA" | never pushed to; hobby-only licence |
| The user's fork | https://github.com/gdluck/PIC_scsgate (GitHub login `gdluck`) | the only place that is pushed to |
| Fork `master` | `c0202b3` = merge of PR #1 (`d427d9a` first pass, `989a638` second pass) | firmware source 544, translator, README |
| Fork `usb-flash-tool` | `820401c`, `d2b72ec`, `277f452` + this file | PR #2, open: https://github.com/gdluck/PIC_scsgate/pull/2 |
| PR #1 | https://github.com/gdluck/PIC_scsgate/pull/1 | merged 2026-10-12 |
| The board | PIC18F26K80 + MCP2200, on the Mac's USB as `/dev/cu.usbmodem00135329031` (115200 8N1) | runs **544** since 2026-10-12 09:05 UTC; bus cable **not** connected |
| The 544 image | Mac: `~/Desktop/test1/PIC_scsgate/BIN/espscsgate_RASPY_8_544.hex`, sha1 `c54829596e50552f1ccb7467515086a034b80f12` | built from `c0202b3`; not in the repo (`BIN/` still holds upstream 543) |
| Toolchain | Mac: `~/Desktop/test1/_toolchain/` (Wine 11 Gcenx build, MPASM Suite 8.92, C18 3.47 lite, `build.sh <project dir>`, README, venv with pyserial, `scripts/probe_log.py`, `scripts/bootloader_test.py`, the two installers) | proven: 543 rebuild byte-identical |
| Mac clone | `~/Desktop/test1/PIC_scsgate` at `c0202b3`, with uncommitted `tools/scsgate_flash.py`, the 544 hex and build outputs (`OBJ/`, `*.cof`, `*.map`, `LIB/*.LST`, `*.XRF`) | nothing committed from the Mac |
| Firmware evidence | project folder `START_HERE.md` (emulation lab of the MyHOMEServer1 translators), `oracle2/` corpus; copied into the fork as `tools/scs_own/corpus/` | the source of every classifier rule |

The cloud session's clone lives in `/home/claude/work/PIC_scsgate` with remotes `origin` = upstream and
`fork` = the user's fork; it is ephemeral.

## 2. What was done, in order

1. **2026-10-11, PR #1 first pass** (`d427d9a`): device-table classifier in `ESPSCSGATE.C` aligned with the
   firmware translators; `tools/scs_own` (C99 and Python SCS <-> OpenWebNet translator, corpus); `tools/scsgate_own.py`;
   README. The user answered "you missed something and slipped several mistakes".
2. **2026-10-11, second pass** (`989a638`): heating-zone rules corrected (zones 1..99, zone#actuator form only in
   96/9D/9E/B7, requests 99/A6/A9 do not create zones), extended D1/D2 frames (only writes kk x2 and answers x4,
   energy A1..AF only, C1/C2 central-unit forms skipped), B8 status 03/04 is "unknown" not dimmer evidence,
   area cover commands B3 (`CmdGruppoTapparelle`), `MsgValido` readability, and the **KW4691 fix** in
   `queueWrite` (interrupts re-enabled after every retry, bus level checked, back-off 8/12/16 ms, 10 retries
   instead of 50). Host harness `tools/devtab_test` rewritten to derive expectations from the firmware's own
   output: 19549/19549 (upstream code: 2616). Translator: C 26809/26809, Python 111820/111820.
3. **2026-10-12 06:58 UTC**: PR #1 merged into the fork's `master`.
4. **2026-10-12, board on USB**: a Remote Control session on the Mac found the port, read version 543,
   proved the bootloader entry (`@` `0x11`), wrote `tools/scsgate_flash.py` and dry-ran it against the 543
   image (451 pages echoed). The user has no Windows and chose Wine ("use wine, i dont have windows").
5. **Toolchain on the Mac** (no system install, no sudo): Homebrew's wine casks are all disabled, so the Gcenx
   Wine 11 stable build was unpacked into `_toolchain`; MPLAB 8.92 came from microchip.com and only its MSI
   was extracted (`msiexec /a`) for the MPASM Suite; microchip.com refuses the C18 download (403), so Microchip's
   own `mplabc18-v3.47-windows-lite-installer.exe` came from the Wayback Machine; its BitRock installer in
   unattended mode installs everything except the compiler (`mcc18*.exe` sit in a "litecompiler" component only
   the GUI selects), so they were taken out of the payload with `bitrock-unpacker`.
6. **Toolchain proof**: the untouched 543 source (`e4e2695`) rebuilt with it is byte-for-byte identical to
   `BIN/espscsgate_RASPY_8.hex` (28828 application bytes `0000`-`709F`, 538 bytes `F000`-`F219`, 7 config
   bytes at `300000`; 0 differing). The 544 changes were also audited for C18 quirks (no integer promotion:
   every new expression is 8-bit safe; declarations at block start): nothing to change.
7. **544 built** from `c0202b3`: 0 errors, only the same warning kinds as 543; 30320 bytes at `0000`-`7673`,
   474 pages, `SCS 80.544` string present, bootloader region and config words identical to 543.
8. **Flashed** after the user typed "go": dry run 474/474 (every `55` echo matched), real pass 474/474 with
   status `00`, board reset, `@q` -> `kSCS 80.544`, `@MA`/`@F0` -> `k`, `@r` -> `0` (empty, no bus). Bootloader
   entered again from 544 and left with `80`: future updates go the same way.
9. **PR #2** opened with `tools/scsgate_flash.py`, `tools/build_mplab8.bat`, `tools/build_wine.sh`,
   `tools/compare_hex.py`, README sections "Building the PIC image" and "Flashing over USB", and this file.

## 3. Rules that keep holding

* Push only to the fork (`git push -u fork <branch>`). Never push to `origin` (upstream). The cloud session's
  stop hook warns "N unpushed commits, no remote branch" because it compares with `origin`: check
  `git rev-parse fork/<branch>` and ignore it.
* Never commit BTicino/Legrand firmware files (programs, images, `firmware_root`). The corpus TSVs (frames and
  messages) are fine and already in the fork.
* Licence: the upstream header allows hobby use only and forbids redistribution without the author's consent.
  Fork and pull requests stay on the user's account; nothing goes upstream unless Guido Pagani agrees.
* GitHub from the cloud: only the attached repository (`gdluck/PIC_scsgate`); no `search_*` tools; GraphQL is
  blocked, so `gh pr create` fails and the REST API is used (`gh api repos/gdluck/PIC_scsgate/pulls --method POST --input body.json`).
* Pull request bodies start with the line `<!-- claude-projects-attribution: {"github_login":"gdluck"} -->` and
  `_Requested by **A** · [project thread](https://claude.ai/code/project/chan_0159fxdtgHJqHFpnbme29u2L?thread=cmsg_0159fxdtgHJqHFpnbme29u2L41hQoJLdY3qckYDNU5A6r2)_`,
  then "Before:" / "After:" paragraphs, one sentence on what it does, a "How" paragraph, and end with the two
  attribution lines the session is given. Commits end with the two trailer lines the session is given
  (`Co-Authored-By` and `Claude-Session`). No model name in anything pushed to the repository.
  Every GitHub comment ends with the "Generated by Claude Code" footer.
* Flashing: a complete dry run (`0x03` + `0x55` echo of every page) before every real write; `--write` repeats
  the dry run itself. Never write an image that was not verified (`tools/compare_hex.py` against the previous
  image: bootloader region `F000`-`FFFF` and config words must be identical). The real write starts only after
  the user has typed **go** in the thread; USB stays plugged in and the Mac awake for the minute it takes. A
  write that stops half-way leaves no working program, and the bootloader is only reachable from a working
  program: a PICkit is the only recovery.
* The session on the Mac hears only what the user types in the thread, not the cloud session's replies. To
  make it do something, ask the user to type the instruction (one word is enough, as with "go").
* `BIN/espscsgate_RASPY_8.hex` in the repository is still the upstream 543 image: do not flash it by mistake.
* Memory is off in this project: keep these notes current instead.

## 4. The firmware logic, in short (details: README.md and the `19.544` comments in `ESPSCSGATE.C`)

* SCS frame: `A8 <body> <chk> A3`, body 4 bytes `dd ss tt vv` or 8 bytes (extended, `D0`..`D5` first byte),
  `chk` = XOR of the body, `A5` = ack. Routed frames: `EC bb 00 00 dd ss 12 cc` through interface `bb`.
* Device table (`OutputMapping`): `x0` ON / `x1` OFF -> switch (first sighting wins); `x3`/`x4`/`AB`/`BB` as a
  command -> dimmer; `1D`..`9D` -> dimmer level (`0D` = plain ON); `08`/`09`/`0A` -> cover; as a **status**
  (`B8` source) `02`..`07`, `0C`, `0F` = unknown, no type evidence; `B1 00` general, `B3 0A` area, `B5 0N`
  group are not devices (area commands move the tracked covers of that area). Heating (`3N` type): zone in the
  second byte from `B4 B5 96 B7 9D 9E 9F BF 90..93`, zones 1..99, `zone#actuator` form (bit 7) only in
  `96 9D 9E B7`; requests `99 A6 A9` create nothing. Extended `D1`/`D2`: only writes (`kk` low nibble 2) and
  answers (4) create devices; system 1 lights/covers (dimension `0D 0D` = dimmer, `09` = cover), system 2
  energy meters `A1`..`AF` (type `0x10`, WHERE `5N`), system 3 heating (`C1`/`C2` dimensions are the central
  unit, skipped). Types: 01 switch, 03 dimmer, 08 cover, 09 cover with position, 0E alarm, 0F heating zone,
  10 energy. `@DFF` clears the table.
* KW4691 / 4691 thermostats: before 544, after a collision `queueWrite` retried up to 50 times every 4 ms with
  all interrupts off, so it never saw the frame it had collided with and fired into the other device's
  repetition, a few pulses at a time; the thermostat's long extended-frame dialogue with its actuator was
  corrupted and it went into error. Now: interrupts back on after every attempt, `INPUT_SCS` checked, silence
  of 4 + 4·retry ms required, 10 attempts. Bit-level driver `LIB/SCS_UART.ASM` untouched. **Not yet observed on
  a live bus** (the cable was never connected during this session).
* Host software notes: `@W` takes a one-digit length (`@W7…` short, `@WB…` extended); `@W11…` is read as length 1
  and puts a lone `1A` byte on the bus. The user's Home Assistant module (`gdluck/scsgate`) does that for
  thermostat commands: it must use `@WB`. Set point `*#4*Z*#14*TTTT*M##` -> `90|91|92 Z 30 T`; `D2 Z 03 34 12 …`
  and `B7 Z 30 …` are the zone's own answers, not commands. `python3 tools/scsgate_own.py --own '<msg>'` prints
  the frame and the `@W` command.
* Bootloader (`LIB/CANREPRO_232_EVO.ASM`, protocol checked on the board): enter from the main program with
  `@` `0x11`; every message `LL 10 07 data…`, `LL` = 2 + data bytes; `00` query -> `04 10 07 00 xx`;
  `01 AL AH 40` opens a 64-byte page, then 8 messages of 8 data bytes; `02 CL CH` (16-bit sum of the 64 bytes)
  writes -> `08 10 07 02 RR CL CH cl ch` (`RR` 00 ok, 01 protected `F000`-`FFFF`, FE/FF checksum, checked before
  any write); `03 CL CH` closes without writing or checking; `55` echoes the buffer (`40` + 64 bytes); `80`
  resets. The second byte of the query answer is stale RAM (`A1`, later `00`): `ReproQuery` stores
  `REPRO_VERSION` one byte beyond what it sends, so the version (`1B`, as in the source) shows as the fourth
  data byte of the first `03` reply. Only `0000`-`EFFF` is sent, page 0 last.

## 5. Build and flash procedure (on the Mac)

```sh
cd ~/Desktop/test1/PIC_scsgate
git fetch https://github.com/gdluck/PIC_scsgate.git master && git checkout FETCH_HEAD      # or the branch to test
../_toolchain/build.sh "$PWD"                      # proven script: MPASM /dRASPBERRY_8, mcc18 -D_RASPBERRY_8 -Ou- -Ot- -Ob- -Op- -Or- -Od- -Opa-, MPLINK /u_CRUNTIME /z__MPLAB_BUILD=1
# alternative from the repo (untested on the Mac so far): WINE=<wine> WINEPREFIX=<prefix> tools/build_wine.sh
python3 tools/compare_hex.py BIN/espscsgate_RASPY_8_544.hex BIN/<new>.hex     # bootloader + config must show 0 differ
python3 tools/scsgate_flash.py --port /dev/cu.usbmodem00135329031 --hex BIN/<new>.hex          # dry run
python3 tools/scsgate_flash.py --port /dev/cu.usbmodem00135329031 --hex BIN/<new>.hex --write  # only after the user's "go"
```

Then `@q` must answer `SCS 80.<version>`; `@` `0x11` must still enter the bootloader (`scripts/bootloader_test.py`),
`80` resets. The port name can change after a re-plug (`ls /dev/cu.usbmodem*`).

## 6. Resume plan, once the bus cable is connected

1. The user writes in the thread that the bus is connected and asks for the capture (the Mac session acts on
   the user's words). On the Mac: `@MA`, `@F0`, `@l` and a capture of a few minutes (`_toolchain/scripts/probe_log.py`
   or `python3 tools/scsgate_own.py --port /dev/cu.usbmodem00135329031`), which prints every frame and its
   OpenWebNet meaning. Expected: frames like `A8 B8 31 12 00 9B A3` (lights), `B4`/`B5` temperature reports and
   `D1`/`D2` dialogues from the thermostats, `A5` acks.
2. After some minutes of traffic, dump the device table: `@z` (ascii) or `@D01` to walk it. Check against the
   plant: lights 01, dimmers 03, covers 08/09, heating zones 0F, energy meters 10; no device at group / area
   bytes, no zone above 99. Each wrong entry is a classifier case to check against the corpus
   (`make -C tools/devtab_test test`) before touching the code.
3. Read the counters with `@Q` (query data, ascii): "write error" = collisions, "read error" = checksum
   failures, UART FERR/OERR, RCON, restart counter. Note them, and read them again after a day.
4. Thermostats KW4691: watch them for days with the host software running as usual. When one goes into error,
   capture the frames around that moment (the gateway's own writes appear in the log in ascii mode) and the
   counters, and look for: bursts of the gateway's writes, the lone `1A` bytes of a `@W11` write from the host
   module, frames repeated many times, `A5` acks the gateway sent itself (auto-ack `@P` / `@N` enabled by the
   host; `@n` turns it off). Fix the host module's `@W11` first if it is still there: that alone puts stray
   bytes on the bus.
5. If errors persist with 544 and a clean host, the next suspects, in order: the collision detection and the
   52 ms tail in `queueWrite` / `scsSendWait` (`ESPSCSGATE.C`, `LIB/SCS_UART.ASM`), the retry back-off values,
   and the filter settings the host selects at start (`@o` / `@` `0x17` presets). Any change goes through the
   same build, compare, dry run and "go" sequence as above, and the retry counter in `@Q` tells whether
   collisions happen at all.
6. Repository housekeeping: merge PR #2 (the user's call); then, if wanted, commit the 544 image as
   `BIN/espscsgate_RASPY_8.hex` from the Mac clone (the user must ask the Mac session to do it, or copy the
   file into a cloud session) and tag the fork `v544`.

## 7. Open items

* PR #2 waits for the user's review and merge (no CI in the repository; nothing to fix).
* `tools/build_wine.sh` and `tools/compare_hex.py` were written in the cloud and not yet run on the Mac; the
  Mac's `_toolchain/build.sh` is the proven build. `tools/scsgate_flash.py` in the repository is the version
  that flashed the board, plus a cosmetic change in how it prints the bootloader version (`277f452`).
* The 544 hex is not in the repository.
* The KW4691 fix is unproven on a live bus; the bus test above is the real acceptance test of this work.
* The Home Assistant module's `@W11` write (outside this repository) still needs fixing to `@WB`.
* A PICkit was never needed; the user did not say whether they own one.

## 8. How to restart a session from nothing

1. Clone the fork (or `git clone PIC_scsgate_2026-10-12.bundle` from the project folder), read `README.md`,
   `tools/README.md` and this file; the firmware evidence is in `tools/scs_own/corpus/` and in the project
   folder's lab (`START_HERE.md`).
2. For anything on the board, start a Remote Control session on the Mac in `~/Desktop/test1` with
   instructions that point at `SCSGATE_SESSION_NOTES.md` and `_toolchain/README`, the port and the rules of
   section 3; remember that it only hears the user's own messages.
3. Run the checks before trusting anything changed: `make -C tools/scs_own test`,
   `python3 tools/scs_own/py/validate_all.py`, `make -C tools/devtab_test test`.
