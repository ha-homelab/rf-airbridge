# Changelog

## Unreleased

### Added

- An optional native Wake-on-LAN action sends a television magic packet from
  the ESP8266's Wi-Fi network. Its target MAC is supplied privately through
  `!secret`; the RF package and existing node behavior are unchanged by default.

- Configurable native ESPHome RM433 button events use the existing decoder and
  repeat guard independently of MQTT availability. Existing `rf/received`
  payloads and motion sensor consumers are preserved. Eight code slots default
  to disabled and must be learned/configured privately for each remote.

### Changed

- Disable the MQTT connection-loss reboot timer so a broker outage does not
  restart local native-API control. API authentication and Wi-Fi settings remain
  unchanged.

### Security

- Replace the obsolete Scorecard CI container with the reviewed, checksum-pinned scanner. Keep the upstream SARIF reporting policy, GitHub Security upload and retained report artifacts. The replaced CI image contained 25 high-severity dependency findings in the recorded scan. The scanner replacement changes CI tooling, not the distributed application runtime. OpenSSF REST publication remains disabled as before.

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
