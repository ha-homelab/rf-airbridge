# Wake a television from the RF node's Wi-Fi network

The optional [Wake-on-LAN package](../packages/wake-on-lan.yaml) adds one
`wake_living_tv` action to the existing ESPHome node. Home Assistant calls it
through the native ESPHome API; the ESP8266 sends a UDP magic packet from its
Wi-Fi interface. No additional board, cable, CC1101 transmission, or SSH relay
is required. The package has no startup, reconnect, or scheduled trigger.

The helper follows the ESP8266 transport used by ESPHome's built-in
`wake_on_lan` button on **ESPHome 2026.8.2**, the version required by this
project's receiver patch. It is a network operation:
the node does not need to be physically close to the television. It must have
working Wi-Fi and a broadcast path to the television's standby network
interface. A routed, isolated, or guest network can prevent delivery.

## Add it to an existing node

Keep the existing node name, credentials, RF settings, motion definitions,
RM433 codes, and transmit actions. Add only the optional package:

```yaml
packages:
  rf_airbridge: !include rf-airbridge/packages/rf-airbridge.yaml
  living_tv_wake: !include rf-airbridge/packages/wake-on-lan.yaml
```

In the private `secrets.yaml`, add `living_tv_mac_address` with the MAC address
of the television's connected network interface. Use the Ethernet MAC when
the television is wired; a Wi-Fi MAC from the same television may differ.
Never commit the populated secrets file, firmware, or raw configuration logs.
The ESPHome configuration dump includes the resolved target address.

Validate and compile with the pinned environment before selecting the node
explicitly for an OTA upload:

```sh
.venv/bin/esphome config device.yaml
.venv/bin/esphome compile device.yaml
.venv/bin/esphome upload device.yaml --device "$RF_NODE_ADDRESS"
```

For a node named `rf`, confirm the action is registered in Home Assistant
after upload, then call:

```yaml
action: esphome.rf_wake_living_tv
```

The action has no arguments: its target is fixed in the private build. It does
not create an MQTT command topic or a duplicate entity. Existing MQTT and
native-API configuration is preserved.

The built-in ESPHome `button` component cannot be added unchanged here: in
2026.8.2 it reserves the word `button`, which is already a parameter of the
existing `send_dooya_code` action. Renaming that parameter would break callers.
The small optional helper preserves every existing RF action signature. A
compile-time check rejects malformed, multicast, broadcast, and all-zero MACs.

## Verification and limits

1. Record the existing native API entities, action signatures, and accepted
   firmware version before updating. Keep the accepted firmware available.
2. Compile the actual private configuration. Check flash/RAM usage and confirm
   the RF settings are unchanged. A successful build does not test delivery.
3. After OTA, compare all existing entity identities and action signatures.
   Confirm that only the new action was added and motion reception resumes.
4. With the television in normal standby and mains power present, invoke the
   action once. A successful API call confirms dispatch, not television wake.
   Verify the actual television state. Passive packet capture can distinguish
   missing dispatch from Wi-Fi broadcast filtering or standby configuration.
5. Test the regular HA television `turn_on` path separately. That HA automation
   may retain an independent infrared `PowerOn` fallback for reliability.

The helper sends a standard magic packet (six `FF` bytes followed
by the target MAC repeated sixteen times) to `255.255.255.255`, UDP port 9.
Its message that a packet is being sent is not an acknowledgement. Wake-on-LAN
cannot wake a television whose mains outlet is off, and some televisions need
their standby network wake option enabled. The action cannot turn the TV off
or report its state. Repeating a magic packet is safe for an already-awake TV;
avoid power-toggle infrared fallbacks, which could switch it back off.

The public validation helper exercises this optional package without a device
or real credentials:

```sh
python tools/validate_firmware.py --config-only --with-wake-on-lan
python tools/validate_firmware.py --with-wake-on-lan
```

These commands never upload firmware or send network wake packets.

References: [ESPHome Wake-on-LAN button](https://esphome.io/components/button/wake_on_lan/),
[version-pinned implementation](https://github.com/esphome/esphome/blob/2026.8.2/esphome/components/wake_on_lan/wake_on_lan.cpp).
