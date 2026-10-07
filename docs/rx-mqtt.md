# Receive RF events over MQTT

The receive bridge publishes RCSwitch frames independently of the existing
ESPHome motion sensors. A newly observed code does not need a new ESPHome binary
sensor or another firmware installation: Home Assistant can match its MQTT
event instead. Keep the existing 15 motion sensor definitions to preserve their
entity identities and behavior.

This implementation targets **ESPHome 2026.8.2**, an ESP8266 NodeMCU, and a CC1101
tuned to **433.92 MHz ASK/OOK**. It uses ESPHome's existing receiver and RCSwitch
decoder, with the existing 30% tolerance. It does not scan other frequencies or
decode every radio protocol.

## Add the receive hook

Include `include/rf_receiver.h` in the ESPHome configuration and give the
existing MQTT component an ID. Keep the current MQTT credentials and discovery
settings; adding a second MQTT component is unnecessary.

```yaml
esphome:
  # Keep the existing node name and other settings.
  includes:
    - include/rf_receiver.h

mqtt:
  id: rf_mqtt
  broker: !secret mqtt_broker
  username: !secret mqtt_username
  password: !secret mqtt_password

switch:
  - platform: template
    name: RF Raw Learning
    id: rf_raw_learning
    optimistic: true
    restore_mode: ALWAYS_OFF
    entity_category: diagnostic

remote_receiver:
  # Merge the hook into the existing receiver; do not create a second receiver.
  pin: GPIO4
  dump: rc_switch
  tolerance: 30%
  filter: 250us
  idle: 4ms
  on_raw:
    then:
      - lambda: |-
          static rf_bridge::Receiver bridge;
          bridge.on_receive(x, id(rf_mqtt), id(rf_raw_learning).state);
```

The snippet demonstrates receive-only integration. When a transmitter shares
GPIO4, retain the main configuration's shared-pin and CC1101 mode-switching
settings rather than replacing them with the simple `pin` line above. Pass its
TX/cooldown guard as the fourth argument:

```cpp
bridge.on_receive(x, id(rf_mqtt), id(rf_raw_learning).state, suppress_rx);
```

`suppress_rx` is a boolean supplied by the caller. A true value discards the
capture before decoding or publishing. The receive helper does not create a
transmit guard itself and does not identify the physical sender of an RF frame.
If the caller needs to exclude its own transmissions, the guard must also cover
any buffered capture or settling time after transmission.

One static `Receiver` instance uses a fixed 2,560-byte scratch buffer. Do not
construct a new instance for each frame or place the buffer on the small
ESP8266 callback stack. The constructor accepts optional source/topic settings:

```cpp
static rf_bridge::Receiver bridge(
    "rf", "rf/received", "rf/received/raw", 30);
```

These strings must have static lifetime. Source IDs accept 1–32 ASCII letters,
digits, underscores, or hyphens. Keep the constructor tolerance synchronized
with the receiver's percentage tolerance. The frequency field is fixed at
433.92 MHz to describe this configuration; update the helper if tuning changes.

## Decoded events

Listen to `rf/received` from the Home Assistant MQTT integration's **Listen to a
topic** tool, then operate a device you own. A synthetic example event is:

```json
{
  "schema": 1,
  "source": "rf",
  "origin": "radio",
  "format": "rc_switch",
  "frequency_mhz": 433.92,
  "boot_id": "0123456789abcdef",
  "sequence": 1,
  "event_id": "rf:0123456789abcdef:1",
  "uptime_ms": 123456,
  "protocol": 1,
  "bits": 24,
  "code": "000000010010001101000101",
  "value": "74565"
}
```

- `code` preserves the exact decoded bit count, including leading zeroes. Match
  `protocol`, `bits`, and `code` together when identifying a device command.
- `value` is a decimal **string**, because 64-bit codes can exceed the exact
  integer range of JSON consumers. Do not convert it to a floating-point value.
- `source` identifies this bridge, not the RF sender. `origin: radio` describes
  the receive path; it does not authenticate a signal or prove an external
  sender when local TX suppression is disabled.
- `boot_id` is a random diagnostic session identifier. `sequence` increases
  for publication attempts, including failed attempts. `event_id` combines the
  bridge, session, and sequence for correlation. They are not security tokens.
- `uptime_ms` is the bridge's 32-bit millisecond uptime and wraps after roughly
  49.7 days. Use Home Assistant's receipt time for wall-clock timestamps.

Every successfully decoded capture is submitted once while MQTT is connected,
including repeated frames and codes already handled by the old motion sensors.
The first matching stock RCSwitch protocol (1–8) wins, matching ESPHome's normal
decoder behavior. A receiver can decode noise or a partial frame; confirm a
new code across repeated intentional device operations before assigning an
automation.

Events use **QoS 0 and `retain: false`**. There is no offline queue or historical
replay. A disconnected broker, a publish failure, or RF reception limits can
lose an event. Do not rely on this stream for guaranteed delivery. MQTT
reconnection must not replay an old receive event as a new button press.

## Why the helper uses `on_raw`

ESPHome 2026.8.2's `on_rc_switch` trigger exposes only a numeric code and protocol;
its `RCSwitchData` omits the bit count. Padding a numeric value to a guessed width
would lose information needed for replay. The helper receives the captured
timings through `on_raw`, then calls the same stock RCSwitch decoder with its
bit-count output parameter. This preserves leading zeroes without replacing
the existing receiver or sensor listeners.

## Unknown raw frames

Enable **RF Raw Learning** temporarily and listen to `rf/received/raw` while
operating an unrecognized device. Only captures that fail all eight stock
RCSwitch decoders go to this topic. The fields shared with decoded events have
the same meaning, with `format: raw`, plus:

```json
{
  "pulse_count": 4,
  "durations_us": [500, -1500, 1500, -4000]
}
```

Positive durations represent marks and negative durations represent spaces, in
microseconds. Captures may include noise and receiver framing effects. Raw
telemetry is diagnostic data, not a promise that replay will control a device.

The helper publishes at most one unknown raw capture per 500 ms. Each complete
capture must have at most 256 pulses; every duration must be nonzero and between
-120,000 and 120,000 microseconds. Out-of-bounds captures are dropped completely,
never truncated. The fixed JSON buffer rejects overflow rather than emitting a
partial payload. Raw learning starts disabled after each restart and does not
change how decoded events or the original sensors work.

The existing `filter: 250us` removes short pulses, and `idle: 4ms` affects frame
boundaries. For example, RCSwitch protocol 7 contains nominal 150 µs pulses,
which this filter can reject. Preserve the working sensor tuning initially;
testing another device may require different timing, modulation, frequency, or
a protocol-specific decoder. FSK devices, rolling-code systems, and signals
outside the configured RF channel are not made compatible by forwarding MQTT.

## Consume one code in Home Assistant

Create a counter helper with entity ID `counter.rf_demo_received`. This example
increments that helper without operating a physical load. Replace the synthetic
payload with the protocol, bit count, and code from your own observed event.

```yaml
alias: RF example - count a learned code
triggers:
  - trigger: mqtt
    topic: rf/received
    value_template: >-
      {{ value_json.protocol | int(0) }}:{{ value_json.bits | int(0) }}:{{ value_json.code | default('') }}
    payload: "1:24:000000010010001101000101"
actions:
  - action: counter.increment
    target:
      entity_id: counter.rf_demo_received
  - delay:
      milliseconds: 750
mode: single
max_exceeded: silent
```

`mode: single` and the delay ignore a burst of repeated RF frames for 750 ms
after a match. They also ignore intentional rapid repeats inside that window;
choose an interval suitable for the device. The receive bridge itself performs
no decoded-frame deduplication, so other consumers can use different policies.

To validate the automation without transmitting RF, publish a synthetic matching
JSON event to the receive topic with **retain disabled**. Verify one increment,
then verify that a different code or protocol does not increment it. Publish a
quick matching burst to test the cooldown, then repeat after 750 ms. A broker
injection tests MQTT → Home Assistant only; separately observe an actual device
produce a received event to prove RF → MQTT.

Do not connect this diagnostic receive topic directly back to a transmit action:
an automatic feedback loop can repeatedly retransmit received traffic. Keep
transmit commands explicit. Store real learned codes and captures privately;
the examples in this repository are synthetic.

## Verification boundaries

`tests/test_receiver_contract.py` checks serialization, 64-bit/leading-zero
preservation, duplicate event identity, offline behavior, TX suppression, and
raw bounds/rate limiting using a controlled decoder and MQTT sink. Those tests
do not validate ESPHome's RF decoder or the physical radio. Compile the full
configuration with ESPHome 2026.8.2, then verify real reception and the existing
motion entities before considering a deployment complete.

References:

- [ESPHome Remote Receiver](https://esphome.io/components/remote_receiver/)
- [ESPHome MQTT](https://esphome.io/components/mqtt/)
- [RCSwitch payload and decoder API, ESPHome 2026.8.2](https://github.com/esphome/esphome/blob/2026.8.2/esphome/components/remote_base/rc_switch_protocol.h)
- [Stock RCSwitch decoder, ESPHome 2026.8.2](https://github.com/esphome/esphome/blob/2026.8.2/esphome/components/remote_base/rc_switch_protocol.cpp)
- [Receiver listener dispatch, ESPHome 2026.8.2](https://github.com/esphome/esphome/blob/2026.8.2/esphome/components/remote_base/remote_base.cpp)
- [Home Assistant MQTT trigger](https://www.home-assistant.io/triggers/mqtt/)
