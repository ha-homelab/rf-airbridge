# Install over USB from a browser

You do not need a local Python environment or a command-line flasher to write
RF Airbridge to its **ESP8266 NodeMCU**. Build your private configuration in
**ESPHome Device Builder**, download its firmware, then use
**[ESPHome Web](https://web.esphome.io/)** to install it over USB.

RF Airbridge uses your MQTT broker, API encryption key, OTA settings and optional
learned RF codes. A release source ZIP is not firmware, and a CI image compiled
with dummy credentials is not a usable installation. Keep personalized binaries
private: they contain those settings. The browser replaces the flashing tools;
it does not invent the missing device configuration.

## First installation

1. Open ESPHome Device Builder in Home Assistant. Add the project's
   `device.example.yaml`, `packages/`, `components/` and `include/` files while
   preserving their relative paths. Use the ESPHome version pinned by this
   release; see the [main setup instructions](../README.md).
2. Configure your own secrets and retain any existing motion-sensor definitions
   when migrating. Validate, then choose **Install → Manual download** for this
   device. Device Builder performs the compilation, so no compiler is needed
   on the computer attached to USB.
3. Connect the matching **ESP8266 NodeMCU** with a USB data cable. Open
   **[ESPHome Web](https://web.esphome.io/)** in current desktop Chrome or Edge,
   select **Connect**, and grant access only to this board's serial port.
4. Choose **Install**, select the ESP8266 firmware `.bin` downloaded in step 2,
   and follow the prompts. Do not choose **Prepare for first use** as a substitute:
   that installs generic onboarding firmware, not RF Airbridge.
5. Reset normally, close the serial connection, and verify Wi-Fi, encrypted
   native API, MQTT reception and the existing sensor entities. Use the
   [receive checks](rx-mqtt.md) before testing any transmit action.

An ESP8266 image starts at `0x0`; ESPHome Web handles this when installing its
ESP8266 firmware download. Do not select an ESP32 factory image, an OTA package
for another application, a source archive, or a `firmware.elf` file.

## Existing devices and later updates

Use the existing private configuration in Device Builder for normal OTA updates.
Back it up before replacing it. A browser USB reinstall can replace settings and
is useful for first installation or recovery; it is not required for every
update. No RF code is transmitted merely by opening the browser installer.

## Troubleshooting

- **Browser reports no Web Serial:** use the HTTPS site in a supported desktop
  browser, outside an embedded app view. iPhone/iPad browsers cannot perform
  this USB installation path.
- **No port:** check that the cable carries data, install the board maker's
  CP210x/CH340 driver if needed, or try another USB port. On Linux, ensure your
  user has access to the serial-device group; do not run the browser as root.
- **Port busy:** close ESPHome logs and other serial programs or browser tabs.
- **Cannot enter download mode:** follow the NodeMCU's BOOT/FLASH and RESET/EN
  procedure; do not connect or short guessed pins on a different board.
- **Flashes but does not join Wi-Fi:** confirm that you selected your compiled
  configuration, not a dummy CI artifact. Check 2.4 GHz Wi-Fi credentials and
  the serial logs.
- **No MQTT or old sensors disappeared:** check the broker settings and retained
  private sensor definitions. Browser flashing does not migrate missing YAML.

See [ESP Web Tools](https://esphome.github.io/esp-web-tools/) for browser support
and [ESPHome Device Builder](https://esphome.io/guides/getting_started_hassio/)
for compilation in Home Assistant.
