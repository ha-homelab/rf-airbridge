# Send Dooya commands from Home Assistant

RF Airbridge exposes `esphome.rf_send_dooya_code` for Dooya's 40-bit frame
format, using ESPHome's native `remote_transmitter.transmit_dooya` encoder.
The action prefix is the ESPHome node name; a node named differently from `rf`
has a different registered action name.

This adds transmission without changing the existing receive decoder, 250 µs
filter, 4 ms idle setting, or legacy motion sensors. It uses the same CC1101
and the existing shared-pin suspend/transmit/resume hooks.

## Action fields

All five fields are required integers:

- `remote_id`: 0–16,777,215 (`0x000000`–`0xFFFFFF`), the 24-bit remote identifier.
- `channel`: 0–255, the next 8 bits.
- `button`: 0–15, the 4-bit button value.
- `check`: 0–15, the final 4-bit check value.
- `repeats`: 1–10 copies of the frame, with a 10 ms gap between copies.

Firmware checks every signed API value before the encoder narrows it to the
wire field. It transmits the supplied `check` nibble; it does not infer or
calculate one. Use the entire tuple captured for the intended command. Do not
assume that a button or check value universally means Open, Close, or Stop.

This example is **synthetic**, not a code captured from a real installation:

```yaml
action: esphome.rf_send_dooya_code
data:
  remote_id: 1193046 # Synthetic example: 0x123456.
  channel: 1
  button: 1
  check: 2
  repeats: 3
```

Calling this action transmits RF. Replace all the example fields with your
private captured values before deliberately testing a device you intend to
operate. Keep those identifiers and captures out of a public repository.

## Power first, then send

If a curtain motor normally has its power socket switched off, the HA action
sequence can power that socket, wait three seconds, then send its captured
Open or Close tuple. [The generic sequence](../examples/dooya-power-sequence.yaml)
is an action-list example, not an automatically enabled schedule:

```yaml
- action: switch.turn_on
  target:
    entity_id: switch.example_curtain_power
- delay:
    seconds: 3
- action: esphome.rf_send_dooya_code
  data:
    remote_id: 1193046
    channel: 1
    button: 1
    check: 2
    repeats: 3
```

Use the captured Open tuple in a morning automation and the captured Close
tuple in an evening automation, preserving the installation's intended
schedule. The three-second delay gives the powered receiver time to start;
it is not proof that every model has finished booting. Confirm the delay with
the actual receiver. For multiple motors, use each motor's captured tuple and
account for the shared transmitter cooldown below.

## One transmitter, one busy window

The RCSwitch and Dooya API actions both validate their input and enter the
**same** `rf_send_job` script. It runs in `mode: single`, selects the requested
encoder, publishes completion, then remains running for a 750 ms cooldown.
Neither format can bypass a transmission or cooldown started by the other.

A request received while this worker is running produces `busy`; it is not
queued or transmitted later. A `send_finished` result is published before the
cooldown finishes, so it does not mean the next command can be accepted
immediately. Allow the additional 750 ms, plus scheduling margin, before the
next explicit command and handle `busy` if other automations share the node.

The worker's serialization is separate from radio reception: the receiver is
restored before completion is published and can receive during the cooldown.
Transmission itself remains synchronous and half duplex. No receive event is
automatically retransmitted.

## Result events and proof limits

The existing `rf/transmit/result` topic carries non-retained QoS 0 results.
Dooya results include `format: dooya` for all outcomes:

- `invalid_request`: one or more fields failed validation; no transmission was
  started for that request.
- `busy`: the shared worker was still transmitting or in its cooldown; the
  request was rejected.
- `send_finished`: the transmit sequence completed and receiver restoration
  ran. It includes the requested fields and `receiver_resumed`.

A synthetic completion example is:

```json
{
  "source": "rf",
  "format": "dooya",
  "status": "send_finished",
  "remote_id": 1193046,
  "channel": 1,
  "button": 1,
  "check": 2,
  "repeats": 3,
  "receiver_resumed": true,
  "delivery_confirmed": false
}
```

RCSwitch results now include `format: rc_switch`, so a consumer can distinguish
the two command families. `delivery_confirmed` remains false. These events
report firmware behavior, not an acknowledgement from the target motor. A
successful HA call, compile, or completion message does not prove that a
curtain moved. Observe the intended receiver independently when commissioning.

## Captures and the unchanged receiver

Dooya's encoder sends a header followed by 24 identifier bits, 8 channel bits,
4 button bits, and 4 check bits. The native encoder supplies the header; do not
pass a guessed raw waveform or reinterpret a partial capture as an RCSwitch
code.

The preserved 4 ms idle threshold is shorter than the native Dooya encoder's
5 ms leading mark. The existing capture path can therefore omit that header
from a recorded data segment. This change deliberately does not adjust
receive timing or add a Dooya decoder to the MQTT receive bridge, because that
would also change reception of the existing motion sensors. Interpret partial
captures with the framing limitation in mind and verify command fields from
repeated captures rather than treating one fragment as authoritative.

This is support for this Dooya frame format, not a claim of compatibility with
all Dooya-branded products, rolling-code systems, other modulation schemes, or
other frequencies. Arbitrary raw-waveform transmission remains unimplemented.

## Validation

The host suite exercises the actual C++ validator across field boundaries and
out-of-range signed values. Package tests verify that both APIs enter the same
guarded worker, retain its trailing 750 ms delay, use the shared transmitter,
and preserve the existing receiver settings. The full ESPHome 2026.8.2 build
checks the native encoder and action-lambda types.

The [earlier live validation](live-validation.md) covers the original RCSwitch
send path and reception recovery. It is not evidence of delivery of a Dooya
command to a target motor.

Sources:

- [ESPHome remote transmitter](https://esphome.io/components/remote_transmitter/)
- [Dooya encoder, ESPHome 2026.8.2](https://github.com/esphome/esphome/blob/2026.8.2/esphome/components/remote_base/dooya_protocol.cpp)
- [Dooya data fields, ESPHome 2026.8.2](https://github.com/esphome/esphome/blob/2026.8.2/esphome/components/remote_base/dooya_protocol.h)
