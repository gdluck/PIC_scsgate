# tools

* `scsgate_own.py` – translate the gateway's serial output (or a log of it) into OpenWebNet, and
  OpenWebNet commands into the frame to write. Uses `scs_own/py`.
* `scs_own/` – the SCS ⇄ OpenWebNet translator recovered from the MyHOMEServer1 firmware: C99 port,
  Python implementation, byte-level documentation, the 26,809-frame corpus and the 111,820 recorded
  firmware answers (`corpus/`) it is validated against.
* `devtab_test/` – compiles the device-table classifier and the area cover command out of
  `../ESPSCSGATE.C` and replays the corpus through them (`make test`).
* `scsgate_flash.py` – flashes a hex image through the board's own serial bootloader (dry run by default,
  `--write` for the real pass).
* `build_mplab8.bat`, `build_wine.sh` – build the RASPY_8 image with the MPLAB 8 command-line tools
  (cmd.exe on Windows or Wine; the shell script drives Wine directly on macOS / Linux).
* `compare_hex.py` – compares two Intel HEX images region by region (application, bootloader, config,
  EEPROM); used to prove a toolchain by rebuilding the stock source against `../BIN`.
