# Preserve reception after transmitting

The existing node connects CC1101 **GDO0 to ESP8266 GPIO4 (D2)**. The same wire
can carry received data and transmit modulation, but the node is half duplex:
it cannot receive while transmitting. No extra data wire is required for this
configuration. The physical wiring is inferred from the existing configuration;
a successful over-air test is the final hardware check.

## Why this local component exists

In ESPHome 2026.8.2, `CC1101Component::begin_tx()` calls `detach_interrupt()` on
`gdo0_pin`. `begin_rx()` returns that pin to input mode but does not reattach the
remote receiver's interrupt handler. The documented automatic single-pin wiring
example therefore needs additional interrupt restoration on this ESP8266 node.
Changing the GPIO direction alone does not restore capture.

Calling `remote_receiver.setup()` after every transmission is not a safe
workaround: it allocates another receive buffer and ISR pin object each time.
The local component instead exposes two allocation-free methods:

- `id(rf_receiver).suspend()` detaches the interrupt, pauses the receiver loop,
  and stops its high-frequency loop request.
- `id(rf_receiver).resume()` makes the pin an input, clears partial frame state,
  samples a fresh time and level baseline, reattaches the original ISR with its
  existing buffer, and resumes the loop.

Calling either method repeatedly is harmless. Any partial frame spanning a
transmission is discarded; subsequent complete received frames are decoded
normally. Existing receiver binary sensors and MQTT capture use this same
receiver instance.

## Configuration

The local component deliberately accepts **only ESPHome 2026.8.2**. The paths
below assume the node YAML lives at the repository root; adapt the local source
path if including the package elsewhere.

```yaml
external_components:
  - source:
      type: local
      path: components
    components: [remote_receiver]

cc1101:
  id: rf_radio
  cs_pin: GPIO15
  gdo0_pin:
    number: GPIO4
    allow_other_uses: true
  frequency: 433.92MHz

remote_receiver:
  id: rf_receiver
  pin:
    number: GPIO4
    allow_other_uses: true
  # Retain the node's existing tolerance, filter, idle and listener settings.

remote_transmitter:
  id: rf_transmitter
  pin:
    number: GPIO4
    allow_other_uses: true
  carrier_duty_percent: 100%
  on_transmit:
    then:
      - lambda: id(rf_receiver).suspend();
      - cc1101.set_idle: rf_radio
      - cc1101.begin_tx: rf_radio
  on_complete:
    then:
      - cc1101.set_idle: rf_radio
      - cc1101.begin_rx: rf_radio
      - lambda: id(rf_receiver).resume();
```

Setting the radio idle **before** changing the shared pin to an output prevents
the ESP8266 and the CC1101 receive output from driving the line concurrently.
The CC1101 component already restores input mode after component setup, so the
transmitter's initial GPIO setup does not leave reception disabled.

## Command validation and proof limits

The HA-facing command must validate before invoking the transmitter: a binary
string of 8–64 bits, an RCSwitch protocol index of 1–8, and a bounded repeat count
(1–10). Keep the code as a string to preserve leading zeros and avoid 64-bit JSON
integer rounding. The upstream runtime treats every non-`0` character as `1`,
so accepting an unchecked string is unsafe. An invalid protocol index must never
index `RC_SWITCH_PROTOCOLS`.

The separate [Dooya action](dooya-transmission.md) validates a 24-bit remote
identifier, 8-bit channel, 4-bit button and check fields, and 1–10 repeats.
Both command families enter the same `mode: single` worker, which uses these
shared transmit hooks and remains busy through a final 750 ms cooldown.

Only the validated call should execute the transmit action. Keep all timing and
mode-change hooks synchronous; do not insert a delayed action between entering
TX and the actual send. After transmission, always restore RX before publishing
completion. Software completion does not prove that a remote device received or
acted on a signal. The CC1101's transmit-state failure is logged by the driver;
it does not return a delivery acknowledgement.

Host tests compile the actual patched receiver source against GPIO and clock
test doubles. They exercise pre-setup calls, idempotence, interrupt detachment,
discarding a partial frame, reattaching the same capture store, allocation-free
repeated cycles, and successful pulse capture after resume. These tests do not
replace a firmware build and a real receive/transmit/receive check.

## Sources

- [ESPHome 2026.8.2 CC1101 implementation](https://github.com/esphome/esphome/blob/2026.8.2/esphome/components/cc1101/cc1101.cpp)
- [ESPHome 2026.8.2 receiver implementation](https://github.com/esphome/esphome/blob/2026.8.2/esphome/components/remote_receiver/remote_receiver.cpp)
- [ESPHome CC1101 wiring documentation](https://esphome.io/components/cc1101/#integration-with-remote-receivertransmitter)
- [Local patch provenance and licenses](../components/remote_receiver/PROVENANCE.md)
