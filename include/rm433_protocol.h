#pragma once

#include <cstdint>
#include <vector>

namespace rf_bridge {

// RM433 uses protocol-1 pulse ratios at approximately 240 us. ESPHome's
// stock protocol 1 assumes 350 us, so its 30% tolerance excludes these frames.
// Accept a complete 24-bit frame and its trailing sync only. Never accept a
// decoded prefix or widen the existing motion sensors' decoder tolerance.
inline bool decode_rm433_24(const std::vector<int32_t> &timings, uint32_t &code,
                            uint32_t &pulse_length_us) {
  if (timings.size() != 50 || timings[48] < 170 || timings[48] > 330 ||
      timings[49] > -4000 || timings[49] < -120000)
    return false;

  uint32_t value = 0;
  uint32_t short_total = 0;
  for (uint8_t bit = 0; bit < 24; ++bit) {
    const int32_t mark = timings[bit * 2];
    const int32_t space = timings[bit * 2 + 1];
    const bool zero = mark >= 170 && mark <= 330 && space <= -540 && space >= -930;
    const bool one = mark >= 540 && mark <= 930 && space <= -170 && space >= -330;
    if (!zero && !one)
      return false;
    // Individual bounds above make this subtraction safe, even for hostile
    // input containing INT32_MIN or INT32_MAX.
    if (mark - space < 800 || mark - space > 1100)
      return false;
    value = (value << 1) | (one ? 1U : 0U);
    short_total += one ? -space : mark;
  }
  code = value;
  pulse_length_us = (short_total + 12) / 24;
  return true;
}

}  // namespace rf_bridge
