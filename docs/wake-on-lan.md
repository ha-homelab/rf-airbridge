# Wake a television from the RF node's Wi-Fi network

The optional [living-room package](../packages/wake-on-lan.yaml) adds
`wake_living_tv`; the independent [LG2 package](../packages/wake-on-lan-lg2.yaml)
adds `wake_lg2`. Include either package or both. Home Assistant calls the actions
through the native ESPHome API; the ESP8266 sends UDP magic packets from its
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
RM433 codes, and transmit actions. Add only the optional packages you need:

```yaml
packages:
  rf_airbridge: !include rf-airbridge/packages/rf-airbridge.yaml
  living_tv_wake: !include rf-airbridge/packages/wake-on-lan.yaml
  lg2_tv_wake: !include rf-airbridge/packages/wake-on-lan-lg2.yaml
```

In the private `secrets.yaml`, add `living_tv_mac_address` for the living-room
package and `lg2_tv_mac_address` for the LG2 package. Each value is the MAC address
of that television's connected network interface. Existing living-room-only
installations need no new secret or configuration. Use the Ethernet MAC when
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

For LG2 on the same node, call the independent action:

```yaml
action: esphome.rf_wake_lg2
```

Each action has no arguments: its target is fixed in the private build. It does
not create an MQTT command topic or a duplicate entity. Existing MQTT and
native-API configuration is preserved. Adding LG2 does not rename or change
`wake_living_tv`, Dooya parameters, receive sensors, or RF action identities.

### Connect the native Home Assistant power-on action

Home Assistant's [webOS turn-on trigger](https://www.home-assistant.io/triggers/webostv.turn_on/)
can delegate the native TV entity's power-on request to this node:

```yaml
alias: LG2 wake through RF node
triggers:
  - trigger: webostv.turn_on
    entity_id: media_player.lg2
actions:
  - action: esphome.rf_wake_lg2
mode: single
```

Replace the entity with the actual native webOS TV entity and the action prefix
with the actual ESPHome node name. Reconcile any existing turn-on automation
instead of adding a duplicate wake path. The automation dispatches the wake
action and returns; a TV controller using HA as fallback should own its bounded
readiness wait. Firmware performs only the finite packet sequence described
below. It does not choose the control route, launch an app, or keep retrying.
Do not use a power-toggle action as the fallback.

For an OttPlay controller without a working LAN wake route, omit the optional
`mac` field from that TV's controller binding and configure its Home Assistant
`fallback` for the native `media_player.lg2` entity. Direct webOS/SSAP control
remains the first route for an awake TV. When wake needs the fallback, HA's
native turn-on request invokes the automation above and the RF node sends the
LAN-side packet sequence. The controller owns readiness checking and app
launch; do not add another wait/retry loop to this automation. See the
[OttPlay television setup](https://github.com/open-ott-play/ottplay-control-server/blob/main/docs/television.md)
for private token files and native TV bindings. Never point the fallback at an
OttPlay proxy entity, which could route the request back to the controller.

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
   Confirm that only the selected wake actions were added and motion reception resumes.
4. With the television in normal standby and mains power present, invoke the
   action once. A successful API call confirms dispatch, not television wake.
   Verify the actual television state. Passive packet capture can distinguish
   missing dispatch from Wi-Fi broadcast filtering or standby configuration.
5. Test the regular HA television `turn_on` path separately. That HA automation
   may retain an independent infrared `PowerOn` fallback for reliability.

Both actions send standard 102-byte magic packets: six `FF` bytes followed by
the target MAC repeated sixteen times, using UDP port 9. Their destinations
and packet counts differ:

- `wake_living_tv` preserves the original behavior: one packet to the limited
  broadcast address `255.255.255.255`.
- `wake_lg2` attempts three subnet-directed packets, approximately 250 ms apart.
  ESPHome's nonblocking delays let the main loop and RF reception continue;
  the finite sequence finishes after approximately 750 ms. Each attempt
  computes its destination from the node's current Wi-Fi IPv4 address and
  netmask. It does not assume a `/24` subnet or embed a private IP address.

A missing or invalid subnet, including `/31` or `/32`, prevents that LG2 attempt
from sending. Wi-Fi and packet-send failures are logged; the next scheduled
attempt checks the current network again. LG2 does not silently switch to
limited broadcast or continue beyond three attempts. The TV must be reachable
through the node's Wi-Fi subnet; broadcasting does not bypass VLAN isolation.

A packet-send log is not an acknowledgement from the TV. Wake-on-LAN
cannot wake a television whose mains outlet is off, and some televisions need
their standby network wake option enabled. The action cannot turn the TV off
or report its state. Repeating a magic packet is safe for an already-awake TV;
avoid power-toggle infrared fallbacks, which could switch it back off.

The public validation helper exercises the optional packages without a device
or real credentials:

```sh
python tools/validate_firmware.py --config-only --with-wake-on-lan
python tools/validate_firmware.py --with-wake-on-lan
python tools/validate_firmware.py --config-only --with-lg2-wake-on-lan
python tools/validate_firmware.py --config-only --with-wake-on-lan --with-lg2-wake-on-lan
python tools/validate_firmware.py --with-wake-on-lan --with-lg2-wake-on-lan
```

The original `--with-wake-on-lan` flag still selects only the living-room action;
`--with-lg2-wake-on-lan` selects LG2 independently. With neither flag, the default
example contains no wake action. CI compiles both packages together to check
coexistence with the RF/Dooya API. These commands never upload firmware or send
network wake packets.

References: [ESPHome Wake-on-LAN button](https://esphome.io/components/button/wake_on_lan/),
[version-pinned implementation](https://github.com/esphome/esphome/blob/2026.8.2/esphome/components/wake_on_lan/wake_on_lan.cpp).
