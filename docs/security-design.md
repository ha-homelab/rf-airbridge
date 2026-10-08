# Security design and verification

## Scope and trust boundaries

The project provides ESP8266/CC1101 RF reception and transmission with ESPHome and Home Assistant.

RF input is unauthenticated and replayable. A matching RF code must not be treated as proof of identity. MQTT carries RF observations; transmit requests use the native ESPHome API through Home Assistant. Restrict MQTT publishers and API access, and keep their credentials outside this repository. Preserve bounded captures, input validation, cooldown and receiver restoration.

## Source and operating documentation

- [device.example.yaml](../device.example.yaml)
- [components/remote_receiver/PROVENANCE.md](../components/remote_receiver/PROVENANCE.md)
- [docs/tx-receiver-patch.md](../docs/tx-receiver-patch.md)
- [docs/home-assistant.md](../docs/home-assistant.md)

## Bluetooth capture HTTPS profile

The optional capture client retains standard aiohttp WSS CA and hostname
verification, then checks exact public-key sizes on the same connection. Its
[supported runtime profile and local verification command](bluetooth.md#capture-from-home-assistant)
requires CPython 3.12+ and the pinned capture dependencies. The owned context
enforces minimum TLS 1.2 and OpenSSL security level 2 without lowering stronger
defaults or expanding the selected cipher list. OpenSSL level 2 alone can
accept an RSA 2047-bit trust anchor; the additional check rejects that boundary.
On CPython 3.12.14 / aiohttp 3.14.4 / cryptography 50.0.2 / OpenSSL 3.5.8,
the actual `_capture` transport rejects trusted RSA 1024- and 2047-bit leaf,
intermediate and root certificates
before the WebSocket HTTP request or administrator-token message, under TLS
1.2 and 1.3. Strong RSA 2048-bit and EC 256-bit fixtures complete authentication and both
subscriptions. Each synthetic chain was separately verified by a test-only
lower-security client to distinguish client rejection from a broken server.
The root is omitted from the offered chain, so these tests also exercise the
selected trust anchor. Unknown issuers and wrong hostnames still fail. The
client uses neither a separate TLS preflight nor global TLS monkey patches.

A failed connection may leave the empty, owner-only output file created by
the capture tool; it contains no captured payload. These are local synthetic
TLS tests, not a physical radio, deployed Home Assistant or firmware test.
Plain HTTP, MQTT and unauthenticated RF need their documented network/access
controls; this HTTPS result does not make those transports confidential.

## Regression evidence

- [tests/test_tx_validation.py](../tests/test_tx_validation.py)
- [tests/test_receiver_patch.py](../tests/test_receiver_patch.py)
- [tests/test_shared_transmitter.py](../tests/test_shared_transmitter.py)
- [tests/test_capture_tls.py](../tests/test_capture_tls.py)

Run the documented commands in [CONTRIBUTING.md](../CONTRIBUTING.md) and the
[CI workflow](../.github/workflows/tests.yml). Preserve negative tests for rejected inputs,
unavailable dependencies, authorization failures and cancellation. A passing
test run describes its fixtures and environment; it does not certify every
upstream service, hardware model or production deployment.

## Remaining security assessment

The existing native receiver, serialization and TX-validation harnesses run under AddressSanitizer and UndefinedBehaviorSanitizer in host CI, with C++ assertions enabled. All 24 host tests also passed locally with sanitizers on 2026-10-08. This covers the exercised host paths with hardware doubles; it does not instrument a live ESP8266 or certify RF behavior. RF replay and third-party ESPHome transport policies need an explicit applicability assessment for cryptography criteria.

Report new issues through [SECURITY.md](../SECURITY.md). An OpenSSF assessment
records evidence and applicability; it is not a guarantee that a system is safe.
