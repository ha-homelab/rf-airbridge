# Security design and verification

## Scope and trust boundaries

The project provides ESP8266/CC1101 RF reception and transmission with ESPHome and Home Assistant.

RF input is unauthenticated and replayable. A matching RF code must not be treated as proof of identity. MQTT carries RF observations; transmit requests use the native ESPHome API through Home Assistant. Restrict MQTT publishers and API access, and keep their credentials outside this repository. Preserve bounded captures, input validation, cooldown and receiver restoration.

## Source and operating documentation

- [device.example.yaml](../device.example.yaml)
- [components/remote_receiver/PROVENANCE.md](../components/remote_receiver/PROVENANCE.md)
- [docs/tx-receiver-patch.md](../docs/tx-receiver-patch.md)
- [docs/home-assistant.md](../docs/home-assistant.md)

## Regression evidence

- [tests/test_tx_validation.py](../tests/test_tx_validation.py)
- [tests/test_receiver_patch.py](../tests/test_receiver_patch.py)
- [tests/test_shared_transmitter.py](../tests/test_shared_transmitter.py)

Run the documented commands in [CONTRIBUTING.md](../CONTRIBUTING.md) and the
[CI workflow](../.github/workflows/tests.yml). Preserve negative tests for rejected inputs,
unavailable dependencies, authorization failures and cancellation. A passing
test run describes its fixtures and environment; it does not certify every
upstream service, hardware model or production deployment.

## Remaining security assessment

The existing native receiver, serialization and TX-validation harnesses run under AddressSanitizer and UndefinedBehaviorSanitizer in host CI, with C++ assertions enabled. All 24 host tests also passed locally with sanitizers on 2026-10-08. This covers the exercised host paths with hardware doubles; it does not instrument a live ESP8266 or certify RF behavior. RF replay and third-party ESPHome transport policies need an explicit applicability assessment for cryptography criteria.

Report new issues through [SECURITY.md](../SECURITY.md). An OpenSSF assessment
records evidence and applicability; it is not a guarantee that a system is safe.
