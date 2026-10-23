#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace rf_bridge::wol {

constexpr int hex_digit(char value) {
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'a' && value <= 'f') return value - 'a' + 10;
  if (value >= 'A' && value <= 'F') return value - 'A' + 10;
  return -1;
}

// Validate before indexing: malformed lengths, separators, and multicast MACs
// cannot become broadcast wake requests. The package enforces this at build time.
template <std::size_t N> constexpr bool valid_mac(const char (&address)[N]) {
  if (N != 18 || address[17] != '\0') return false;
  bool nonzero = false;
  for (std::size_t i = 0; i < 6; ++i) {
    const auto offset = i * 3;
    const int high = hex_digit(address[offset]);
    const int low = hex_digit(address[offset + 1]);
    if (high < 0 || low < 0) return false;
    if (i < 5 && address[offset + 2] != ':') return false;
    const int octet = high * 16 + low;
    if (i == 0 && (octet & 1)) return false;
    nonzero |= octet != 0;
  }
  return nonzero;
}

using MagicPacket = std::array<uint8_t, 102>;

template <std::size_t N> constexpr MagicPacket magic_packet(const char (&address)[N]) {
  MagicPacket packet{};
  if (!valid_mac(address)) return packet;
  for (std::size_t i = 0; i < 6; ++i) packet[i] = 0xff;
  for (std::size_t repetition = 0; repetition < 16; ++repetition) {
    for (std::size_t octet = 0; octet < 6; ++octet) {
      const auto offset = octet * 3;
      packet[6 + repetition * 6 + octet] = static_cast<uint8_t>(
          hex_digit(address[offset]) * 16 + hex_digit(address[offset + 1]));
    }
  }
  return packet;
}

}  // namespace rf_bridge::wol
