# Local receiver patch

This directory vendors the five files in ESPHome's `remote_receiver` component
from **ESPHome 2026.8.2**, copied from the installed 2026.8.2 image and checked
against the upstream release. Original file hashes are in
[`upstream-sha256.json`](upstream-sha256.json).

Upstream: <https://github.com/esphome/esphome/tree/2026.8.2/esphome/components/remote_receiver>

Modified on 2026-10-06:

- `remote_receiver.h`: declare ESP8266-only `suspend()` and `resume()` methods,
  and track whether capture is suspended.
- `remote_receiver.cpp`: detach the capture interrupt during transmission;
  discard a partial capture and reattach the existing ISR and buffer afterwards;
  guard `loop()` while suspended. Repeated suspend/resume calls are idempotent.
- `__init__.py`: reject builds with an ESPHome version other than 2026.8.2.

The ESP32, LibreTiny and RP2 receive paths are unchanged. The new methods are
available only in ESP8266 builds. Rebase and test before changing ESPHome versions.

The upstream [`LICENSE`](LICENSE) is included verbatim. ESPHome's **C++ runtime
files are GPLv3**; its **Python files are MIT**. Those licenses apply to the
respective copied files and modifications. A repository-wide license must not
override these third-party licenses. Copyright (c) 2019 ESPHome.
