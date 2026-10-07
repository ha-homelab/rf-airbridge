# Live validation — 2026-10-06

RF Airbridge was installed by OTA on the original ESP8266 NodeMCU and CC1101
node, using the public implementation at
[`5337ae7`](https://github.com/ha-homelab/rf-airbridge/commit/5337ae7) with the
deployment's private credentials and existing sensor definitions. The node
booted ESPHome **2026.8.2**, reconnected to Home Assistant, and published real
received radio frames to MQTT.

This record describes completed live checks and their limits. It contains no
real received codes, network identifiers, credentials, or household locations.
The receive stream, HA example, and transmit/reception-recovery path were
tested. Independent confirmation of delivery to a target RF appliance was not
available and is not claimed.

## Firmware and existing sensors

- OTA installation completed successfully on the actual ESP8266/CC1101 node.
- The running ESPHome version is 2026.8.2.
- All **15 existing motion binary sensor definitions** were preserved, and
  all **15 corresponding HA entities** were online at the final check.
- Existing connectivity settings were unchanged. Four previously disabled
  automations remained disabled.

Preserving the definitions and reconnecting does not prove that every one of
the 15 physical sensors was individually activated during this validation.
The receive observations below demonstrate activity from the monitored radio
environment without publishing private device identifiers.

## Real radio reception and MQTT

The initial **180-second** live observation captured:

- **233 decoded MQTT events** from real radio reception.
- **11 distinct protocol/code pairs**.
- **209 frames** whose code matched the set configured in the 15 existing
  motion sensor definitions.
- **24 other decoded frames**, demonstrating that the stream is not limited
  to the configured sensor-code allowlist.
- **233 unique event IDs** across the 233 decoded events.
- **Zero retained events** in this observation.

The 24 unmatched frames are not 24 identified new devices, nor proof that every
unmatched frame is valid. Repeats, noise, or partial decoding can appear in a
receive stream. A new device should be identified by repeatedly
operating it and comparing the observed protocol, bit length, and complete
code, as described in [receive learning](rx-mqtt.md).

These were actual RF-to-MQTT observations. They were not synthetic messages
injected into the broker. Unique event IDs identify separate observations;
they do not mean that every observation contains a different device code.

## Optional raw learning

Raw learning was enabled briefly and produced **two raw-frame events**. It was
then switched **off again**. This establishes that the optional raw publication
path operated on the physical node, rather than merely that the switch could
be enabled.

The publication limits are covered separately by host tests. This short live
sample does not exhaustively test every limit or identify the raw signals'
senders. Raw learning does not add arbitrary raw-waveform transmission.

## Home Assistant consumption

The deterministic MQTT-to-HA test succeeded: a synthetic matching event
incremented the example counter from **2 to 3**. Its automation trace contains
the `synthetic-mqtt-only` marker and reached the second action (`action/1`),
the repeat-cooldown delay, after the counter action.

This tests broker delivery, the configured match, and the counter action. The
separate natural-radio capture above proves RF-to-MQTT reception. Do not
describe the synthetic counter test as a natural radio event, or the fact that
the delay action was reached as an exhaustive live test of repeat suppression.
Host tests cover nonmatching inputs and the configured cooldown structure;
they do not simulate Home Assistant's live scheduling. Further live cases can
be recorded independently.

The example's action increments a counter; it does not operate a physical
load. See [the HA setup and test procedure](home-assistant.md).

### Package-merge issue discovered during deployment

The initial script field used the valid-looking empty selector mapping
`text: {}`. In this deployment's Home Assistant package merge, that empty
mapping was dropped, leaving an empty `selector` and an unavailable transmit
script. The fix gives the selector an explicit, nonempty setting:

```yaml
selector:
  text:
    multiline: false
```

This preserves the intended text selector through the package merge. The
public fix was merged in
[pull request #2](https://github.com/ha-homelab/rf-airbridge/pull/2), at
[`adf9c0f`](https://github.com/ha-homelab/rf-airbridge/commit/adf9c0fdc025566754ca63e19557433c1785b2ed),
after its checks passed. The corrected private HA package was installed with
an atomic file replacement. The installed-configuration check reported zero
errors, a guarded script reload succeeded, and the HA transmit wrapper was
registered before testing.

## Transmission and reception recovery

Two rejection paths were checked:

- An invalid HA wrapper request returned HTTP 200, but its script trace
  aborted at `sequence/0/then/0`, before the transmit action. No transmit result
  was observed. HTTP status alone is therefore not a sufficient indication
  that this HA script accepted or completed a command.
- A direct native ESPHome request with invalid protocol `0` produced
  `invalid_request`, confirming the firmware-side validation path.

A valid synthetic **64-bit code**, **protocol 1**, and **3 repeats** was then
sent through `script.rf_send_code`. The firmware published `send_finished`
with `receiver_resumed: true` and `delivery_confirmed: false`.

The separate **120-second transmit-validation capture** recorded **198 natural
RF receive frames before the send and 198 after it**, one transmit result, and
zero retained messages. The first post-send receive event was observed about
**3.927 seconds after the send**. The receive events had the same `boot_id`
before and after transmission: reception recovered without rebooting the node.

The device logged one API-operation warning of **334 ms** during the
synchronous send. The send path completed and real reception resumed; the
timing warning was not a failed transaction. This also illustrates the brief
blocking and half-duplex behavior of this ESP8266 implementation: the shared
radio is not receiving while it transmits.

No independent target RF receiver/appliance was available for this test.
`send_finished` and post-transmit reception establish software-path completion
and receiver recovery, not that a target appliance received the signal or
acted on it. The `delivery_confirmed: false` field preserves that distinction.

## Final state and proof limits

- The original 15 HA sensor entities were online, with their definitions and
  connectivity settings preserved.
- Raw learning was off, and the four previously disabled automations remained
  off.
- The real RF-to-MQTT stream and synthetic MQTT-to-HA example were verified
  separately.
- Input rejection, valid send-path completion, and real reception after the
  send were verified without a reboot.
- Delivery to an independent target appliance was **not tested**.

Host tests and the full firmware build remain distinct evidence from these
live checks. The [receiver patch documentation](tx-receiver-patch.md) describes
what its host tests cover and why a post-transmit hardware receive check matters.
