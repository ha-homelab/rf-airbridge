#pragma once

#include <WiFiUdp.h>
#include "esphome/components/network/util.h"
#include "esphome/core/log.h"
#include "wol_packet.h"

namespace rf_bridge::wol {

// Match the ESPHome 2026.8.2 ESP8266 WoL transport without loading the button
// component: its domain name conflicts with the existing Dooya `button` argument.
inline bool send_magic_packet(const MagicPacket &packet) {
  constexpr auto TAG = "rf.wake_on_lan";
  if (!esphome::network::is_connected()) {
    ESP_LOGW(TAG, "Wi-Fi unavailable; wake packet not sent");
    return false;
  }
  WiFiUDP sender;
  const IPAddress broadcast(255, 255, 255, 255);
  for (const auto &address : esphome::network::get_ip_addresses()) {
    if (!address.is_ip4()) continue;
    if (sender.beginPacketMulticast(broadcast, 9, address, 128) == 0) continue;
    const auto written = sender.write(packet.data(), packet.size());
    const auto sent = sender.endPacket();
    if (written != packet.size() || sent == 0) {
      ESP_LOGW(TAG, "Wake packet send failed");
      return false;
    }
    ESP_LOGI(TAG, "Wake packet sent; target delivery is not confirmed");
    return true;
  }
  ESP_LOGW(TAG, "No IPv4 interface available for wake packet");
  return false;
}

}  // namespace rf_bridge::wol
