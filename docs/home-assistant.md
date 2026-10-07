# Use received RF codes and send commands from Home Assistant

The bridge publishes received RC-Switch frames on `rf/received`. Home Assistant
can match a new device there without adding another hardcoded binary sensor to
the ESPHome firmware. The existing motion sensors can continue to work alongside
this event stream.

The [example package](../examples/home-assistant.yaml) creates one counter, one
receive automation, and one transmit script. The receive example only increments
`counter.rf_received_example`; it does not switch a load or retransmit a code.
The transmit script does nothing until explicitly called.

## Install the package

1. Connect the RF node and Home Assistant to the same MQTT broker. Keep broker
   credentials in the local secret store.
2. Keep the node registered in Home Assistant's ESPHome integration. MQTT carries
   received events; the native ESPHome API carries transmit requests.
3. Copy the example file to `packages/rf_bridge.yaml` in the Home Assistant
   configuration directory. If packages are not enabled, merge this into the
   existing `homeassistant:` section rather than adding a second section:

   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```

4. Run Home Assistant's configuration check. Load the new counter, scripts, and
   automations with their supported YAML reload actions, or perform a controlled
   Home Assistant restart if needed for the installation. When reloading scripts
   or automations, first let any running actions finish.
5. Confirm the counter and automation are present. In **Developer tools >
   Actions**, confirm that `esphome.rf_send_rf_code` is registered. The `rf`
   prefix comes from the ESPHome node name; adjust the example if your registered
   action uses a different prefix.

In an installation that already uses `!include_dir_named packages`, this is one
new package file. Do not duplicate it in the separate automation or script
libraries, and do not edit an unused `automations.yaml` or `scripts.yaml` file.

If you prefer a UI-owned helper, first create a Counter helper with entity ID
`counter.rf_received_example`, initial value 0, step 1, and state restoration
enabled. Then remove the example's top-level `counter:` block before installing
the package. Keep one owner for the helper: do not define the same counter in
both storage/UI configuration and YAML. Creating a helper through the UI avoids
depending on a YAML reload action that the counter integration may not provide.

## Identify a device

Open **Settings > Devices & services > MQTT > Configure** and listen to
`rf/received`. Operate one RF device several times and compare its events. A
synthetic example looks like this:

```json
{"source":"rf","origin":"radio","format":"rc_switch","protocol":1,"code":"000000010010001101000101","bits":24,"sequence":1,"uptime_ms":12345,"event_id":"example-only"}
```

Keep `code` as a **string**, including leading zeroes. Match `source`, `format`,
`protocol`, `bits`, and `code`, as the package does. `sequence`, `uptime_ms`, and
`event_id` describe an observation; they are not the device's permanent address.
One button press can produce several repeated frames. Two different buttons may
share some bits while using different complete codes.

Replace only the synthetic code, protocol, and bit length in your local copy of
the example condition. Then operate the identified device and watch the counter
and the automation's **Traces**. After verifying the match, replace the counter
action with the intended action for that device.

The example ignores malformed JSON, unrelated formats, and nonmatching codes.
Its `mode: single` and final 750 ms delay suppress further matches for 750 ms
after the first accepted event. This is a fixed interval, not a timer extended
by every repeat: a longer button hold may produce another count later.

Messages use QoS 0 and are not retained. They represent live observations, not a
reliable event history or a current on/off state. Do not infer that a device is
off just because no new code has arrived. If someone previously published a
retained message on the same topic, remove that retained message at the broker
before enabling an action that controls equipment.

## Test the receive automation without transmitting RF

In **Developer tools > Actions**, run this once after loading the package. It
publishes only an MQTT message and should increment the example counter by one:

```yaml
action: mqtt.publish
data:
  topic: rf/received
  qos: 0
  retain: false
  payload: >-
    {"source":"rf","origin":"radio","format":"rc_switch","protocol":1,"code":"000000010010001101000101","bits":24,"sequence":0,"uptime_ms":0,"event_id":"manual-ha-test"}
```

This tests the broker-to-automation path. It does not prove radio reception. The
`origin` field describes the expected payload format; it is not authentication.
The topic's publishers must be trusted. Once you change the automation to a real
code and a real action, do not use a matching synthetic test unless you intend
to run that action.

## Transmit a selected code

Open **Developer tools > Actions**, select `script.rf_send_code`, and provide:

- **Binary code:** the exact captured bit string, with leading zeroes.
- **RC-Switch protocol:** the captured protocol number, from 1 to 8.
- **Repeats:** 1 to 10; the script defaults to 3 if omitted.

Calling the script transmits over the air and can operate a matching receiver.
Choose a known code for a device you intend to control. The synthetic receive
example is not a commissioning transmit command.

The script validates its inputs and calls `esphome.rf_send_rf_code`. In YAML,
quote literal codes and pass `code`, `protocol`, and optionally `repeats` under
the script action's `data` mapping. Invalid code lengths, nonbinary text, and
out-of-range protocol/repeat values fail before the ESPHome action is called.
Home Assistant records the validation stop in the script trace; its top-level
service call can still return normally. Inspect that trace when testing invalid
inputs instead of relying on the HTTP response alone.

The native action in this project has no application-level response. A completed
Home Assistant call means the request was dispatched; it does **not** confirm
that the intended appliance received or acted on it. Check the intended device
and the node's logs. RF receive is paused while this shared CC1101 data pin is
used for transmission, then restored. Do not wire `rf/received` straight back to
the transmit script: doing so creates repeats and can form an RF feedback loop.

## Boundaries and troubleshooting

- **No event for a device:** a frequency match alone is insufficient. The
  configured modulation, pulse timings, and supported decoder must also match.
  An optional raw capture can help inspect unknown pulse trains, but does not
  turn encrypted, rolling-code, or unsupported protocols into RC-Switch codes.
- **Several counts per hold:** the sender may repeat longer than 750 ms. Tune
  the automation's interval for that device after checking its behavior.
- **Transmit action missing:** check that the new firmware is installed and the
  ESPHome integration is connected, then use the exact action name registered
  for the node. An MQTT connection alone does not register the native API action.
- **Call completes but nothing happens:** inspect the firmware's transmit log,
  confirm the intended receiver's frequency and protocol, and observe the
  receiver. Successful software dispatch alone is not an RF-range test.
- **Roll back only this example:** remove its package file and reload the
  affected domains or restart Home Assistant. Keep the existing motion sensor
  automations and ESPHome node configuration in place.

## References

- [Home Assistant MQTT triggers](https://www.home-assistant.io/triggers/mqtt/)
- [Home Assistant packages](https://www.home-assistant.io/docs/configuration/packages/)
- [Home Assistant automation modes](https://www.home-assistant.io/docs/automation/modes/)
- [Home Assistant script fields](https://www.home-assistant.io/integrations/script/)
- [ESPHome native API actions](https://esphome.io/components/api/#user-defined-actions)
