#pragma once

#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#include "esphome/components/network/util.h"
#include "esphome/core/log.h"
#include "wol_packet.h"

namespace rf_bridge::wol {

// Match the ESPHome 2026.8.2 ESP8266 WoL transport without loading the button
// component: its domain name conflicts with the existing Dooya `button` argument.
inline bool send_magic_packet_to(const MagicPacket &packet, const IPAddress &broadcast) {
  constexpr auto TAG = "rf.wake_on_lan";
  if (!esphome::network::is_connected()) {
    ESP_LOGW(TAG, "Wi-Fi unavailable; wake packet not sent");
    return false;
  }
  WiFiUDP sender;
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

// Preserve the original living-room action's single limited-broadcast packet.
inline bool send_magic_packet(const MagicPacket &packet) {
  return send_magic_packet_to(packet, IPAddress(255, 255, 255, 255));
}

inline bool subnet_broadcast(const IPAddress &address, const IPAddress &mask, IPAddress &broadcast) {
  uint32_t mask_bits = 0;
  uint32_t address_bits = 0;
  for (size_t i = 0; i < 4; ++i) {
    mask_bits = (mask_bits << 8) | mask[i];
    address_bits = (address_bits << 8) | address[i];
  }
  const uint32_t host_bits = ~mask_bits;
  // Reject missing/noncontiguous masks and /31-/32 networks, which have no
  // usable broadcast. Never fall back to a guessed /24 or a unicast target.
  if (mask_bits == 0 || host_bits < 3 || (host_bits & (host_bits + 1)) != 0 ||
      address[0] == 0 || address[0] >= 224 || (address_bits & host_bits) == 0 ||
      (address_bits & host_bits) == host_bits)
    return false;
  const uint32_t target = address_bits | host_bits;
  broadcast = IPAddress(static_cast<uint8_t>(target >> 24), static_cast<uint8_t>(target >> 16),
                        static_cast<uint8_t>(target >> 8), static_cast<uint8_t>(target));
  return true;
}

// Some standby network stacks ignore the limited-broadcast destination but
// accept their subnet's directed broadcast. Compute it from the active station
// lease so DHCP/netmask changes do not leave a hardcoded private destination.
inline bool send_subnet_magic_packet(const MagicPacket &packet) {
  IPAddress broadcast;
  if (!subnet_broadcast(WiFi.localIP(), WiFi.subnetMask(), broadcast)) {
    ESP_LOGW("rf.wake_on_lan", "No valid station subnet available for directed wake");
    return false;
  }
  return send_magic_packet_to(packet, broadcast);
}

}  // namespace rf_bridge::wol
