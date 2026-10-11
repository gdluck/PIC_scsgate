# tools

* `scsgate_own.py` – translate the gateway's serial output (or a log of it) into OpenWebNet, and
  OpenWebNet commands into the frame to write. Uses `scs_own/py`.
* `scs_own/` – the SCS ⇄ OpenWebNet translator recovered from the MyHOMEServer1 firmware: C99 port,
  Python implementation, byte-level documentation and the 26,809-frame validation corpus.
* `devtab_test/` – compiles the device-table classifier out of `../ESPSCSGATE.C` and replays the corpus
  through it (`make test`).
