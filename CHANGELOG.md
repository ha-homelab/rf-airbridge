# Changelog

## Unreleased

### Added

- Configurable native ESPHome RM433 button events use the existing decoder and
  repeat guard independently of MQTT availability. Existing `rf/received`
  payloads and motion sensor consumers are preserved. Eight code slots default
  to disabled and must be learned/configured privately for each remote.

### Changed

- Disable the MQTT connection-loss reboot timer so a broker outage does not
  restart local native-API control. API authentication and Wi-Fi settings remain
  unchanged.

### Security

- Bluetooth capture checks exact key sizes in the verified HTTPS certificate
  chain before its HTTP upgrade or token exchange. This rejects RSA keys below
  2048 bits, including the 2047-bit boundary accepted by some OpenSSL defaults.
  CA and hostname verification remain enabled. HTTPS redirects that end on
  plaintext HTTP cannot receive the administrator token.

### Upgrade

- Install the hash-locked `requirements-capture.txt` in a separate CPython 3.12+
  environment. HTTPS capture now requires `cryptography` and a runtime exposing
  its verified certificate chain. Replace weak server/issuer keys instead of
  disabling verification. See [the capture profile](docs/bluetooth.md#capture-from-home-assistant).
- The Bluetooth capture changes do not affect existing captures. Installing
  source changes alone does not update or operate any device.
