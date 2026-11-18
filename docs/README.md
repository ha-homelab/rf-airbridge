# Documentation

An ESP8266 and CC1101 bridge that receives and sends 433 MHz RF codes for Home
Assistant, with the wiring and validation records behind it.

## Use it

- [Install over USB from a browser](browser-install.md) — flashing without a local Python environment.
- [Use received RF codes and send commands from Home Assistant](home-assistant.md) — the `rf/received` topic and the commands.
- [Receive RF events over MQTT](rx-mqtt.md) — publishing RC-Switch frames independently of the existing bridge.
- [Send Dooya commands from Home Assistant](dooya-transmission.md) — the `esphome.rf_send_dooya_code` service and its 40-bit frame.
- [Wake a television from the RF node's Wi-Fi network](wake-on-lan.md) — the optional living-room package.

## Hardware

- [Bluetooth alongside RF Airbridge](bluetooth.md) — the installed NodeMCU v2 and CC1101 combination.
- [Preserve reception after transmitting](tx-receiver-patch.md) — the shared GDO0 wire and how reception survives a send.

## Verification

- [Live validation — 2026-10-06](live-validation.md) — the OTA install on the original NodeMCU and CC1101.
- [Quality and assessment scope](quality.md) — the RF extension, examples, capture tools and bundled receiver code.
- [Security design and verification](security-design.md) — what the RF receive and transmit path does.
- [OpenSSF evidence](openssf-evidence.md) — the proposed Passing assessment in `.bestpractices.json`.
