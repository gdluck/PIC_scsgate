# tools

* `scsgate_own.py` – translate the gateway's serial output (or a log of it) into OpenWebNet, and
  OpenWebNet commands into the frame to write. Uses `scs_own/py`.
* `scs_own/` – the SCS ⇄ OpenWebNet translator recovered from the MyHOMEServer1 firmware: C99 port,
  Python implementation, byte-level documentation, the 26,809-frame corpus and the 111,820 recorded
  firmware answers (`corpus/`) it is validated against.
* `devtab_test/` – compiles the device-table classifier and the area cover command out of
  `../ESPSCSGATE.C` and replays the corpus through them (`make test`).
