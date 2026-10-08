# Security design and verification

## Scope and trust boundaries

The project provides ESP8266/CC1101 RF reception and transmission with ESPHome and Home Assistant.

RF input is unauthenticated and replayable. A matching RF code must not be treated as proof of identity. MQTT and Home Assistant commands can cause radio transmission; restrict their publishers and keep broker credentials outside this repository. Preserve bounded captures, input validation, cooldown and receiver restoration.

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

Review the vendored C++ receiver with memory-safety analysis and document its result. RF replay and third-party ESPHome transport policies need an explicit applicability assessment for cryptography criteria.

Report new issues through [SECURITY.md](../SECURITY.md). An OpenSSF assessment
records evidence and applicability; it is not a guarantee that a system is safe.
