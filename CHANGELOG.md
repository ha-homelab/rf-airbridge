# Changelog

## Unreleased

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
- Firmware, RF command behavior and existing captures are unchanged. These
  source changes do not update or operate any device.
