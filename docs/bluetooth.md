# Bluetooth alongside RF Airbridge

## Hardware boundary

The installed RF Airbridge hardware is an **ESP8266 NodeMCU v2 with a CC1101**.
The ESP8266 has Wi-Fi but no Bluetooth radio. The CC1101 is a sub-GHz
transceiver, not a 2.4 GHz Bluetooth adapter. Adding `bluetooth_proxy:` to this
firmware cannot add Bluetooth support. Keep the working RF firmware and use a
separate compatible Bluetooth device.

An ESP32 with BLE support can provide an ESPHome Bluetooth proxy. Check the
exact chip: the ESP32 family includes variants without Bluetooth. Do not flash
an ESP32 image onto the ESP8266. A future migration of RF Airbridge itself to
ESP32 also needs new pin assignments and RF receive/transmit regression tests;
the current receiver patch is validated on ESP8266 only.

Home Assistant can use other supported proxies too. An Echo Dot 2 running
EchoLocal exposes a Bluetooth proxy switch through its ESPHome-compatible API.
The inspected EchoLocal implementation forwards BLE advertisements and raw
advertising data. It does **not** expose active GATT connections or a generic
light-command advertising action. Receiving packets does not prove that a
proxy can transmit the commands needed by a lamp.

## Identify the lamp before choosing an integration

A remote with power, brightness and warm/cool buttons does not identify its
radio protocol. A Bluetooth label on a lamp module is useful evidence, but
does not establish whether the physical remote uses standard BLE, a proprietary
2.4 GHz protocol, sub-GHz RF, or infrared.

1. Record the lamp, receiver and remote model or regulatory identifiers if
   accessible without opening a mains-powered enclosure. Record any app name.
2. Verify that Home Assistant has a running Bluetooth scanner and that it sees
   ordinary nearby BLE traffic before testing the remote.
3. Keep the remote near the scanner. Record a quiet baseline, then press only
   **On** three times, two seconds apart. Note the times and whether the lamp
   responds. Repeat in separately labelled captures for Off, brighter, dimmer,
   warmer and cooler after identifying a candidate signal.
4. Match repeated packet content and timing to the button presses. Do not pick
   an unrelated nearby device based solely on signal strength. A negative BLE
   capture does not prove that the remote is not Bluetooth: range, scan duty
   cycle, active connections and protocol support can affect visibility.

For a supported BLE GATT lamp, use its Home Assistant integration and a proxy
that supports active connections. For lamps controlled by proprietary BLE
advertising, the third-party **BLE ADV Ceiling Fan / Lamps** integration can
recognize several protocol families. It requires a suitable transmitter, such
as an ESP32 running `ble_adv_proxy`, not just the standard receive/proxy
component. Physical remote compatibility must be tested.

Avoid blind pairing or replaying unidentified packets. Reuse an existing
remote identity only after a consistent decode, and keep real identifiers,
captures and keys out of this public repository.

## Capture from Home Assistant

[capture_bluetooth.py](../tools/capture_bluetooth.py) subscribes to Home
Assistant's scanner inventory and advertisement stream for a bounded period.
It does not enable adapters, install integrations, pair devices, or transmit
commands. Use a Home Assistant administrator access token because these
WebSocket commands require administrative access. The Python environment needs
`aiohttp` (available in the ESPHome environment used by this project).

```sh
mkdir -p captures
chmod 700 captures
read -r -s -p 'Home Assistant token: ' HA_TOKEN
export HA_TOKEN
python tools/capture_bluetooth.py \
  --url http://homeassistant.local:8123 \
  --seconds 60 \
  --output captures/lamp-on.jsonl
unset HA_TOKEN
```

The command uses Bash's `read` syntax. Prefer HTTPS when accessing Home
Assistant outside a trusted local connection. The output is created with mode
0600 and existing files are never overwritten. The ignored `captures/`
directory is for private local use. Captures contain nearby device identifiers
and payloads; do not attach them unredacted to public issues.

Home Assistant may cache or coalesce observations, and the first event may
include previously seen devices. `received_at` is the capture's UTC timestamp;
the advertisement's own `time` value is supplied by Home Assistant. This is an
application-level observation stream, not a complete over-the-air packet trace.

The capture tool was exercised against a live Home Assistant instance on
2026-10-06: both subscriptions were acknowledged, scanner and advertisement
events were saved, the output mode was 0600, and the token was absent from the
file. Automated tests cover authentication and subscription rejection, missing
acknowledgements, file overwrite protection, and the read-only request set.
These checks validate capture infrastructure, not compatibility with an
unidentified lamp.

## Acceptance and rollback

Before calling a lamp integration complete, verify real On and Off responses,
two brightness levels, both warm and cool temperature settings, continued
operation of the original remote, and recovery after reconnecting the proxy.
Record observed behavior separately from the requested HA state. Many BLE
advertising integrations report assumed state without an acknowledgement.
Check that the existing RF motion sensors and curtain actions remain available.

For a proxy-only change, record its previous switch state so it can be restored.
For a new ESPHome transmitter, retain its original YAML, secrets and working
firmware privately before any upload. Do not change the RF node merely to add
an independent Bluetooth path.

## References

- [ESP8266 hardware](https://www.espressif.com/en/products/socs/esp8266)
- [CC1101 datasheet](https://www.ti.com/lit/ds/symlink/cc1101.pdf)
- [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy/)
- [Home Assistant Bluetooth](https://www.home-assistant.io/integrations/bluetooth/)
- [EchoLocal Bluetooth implementation](https://github.com/ygelfand/echolocal/blob/main/internal/feature/bluetooth/bluetooth.go)
- [BLE ADV Ceiling Fan / Lamps](https://github.com/NicoIIT/ha-ble-adv)
- [ESPHome BLE advertising proxy](https://github.com/NicoIIT/esphome-ble_adv_proxy)
