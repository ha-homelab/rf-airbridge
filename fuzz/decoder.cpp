#include "rm433_protocol.h"
#include <fuzzer/FuzzedDataProvider.h>
#include <cassert>
#include <cstdint>
#include <vector>
#include <string>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  FuzzedDataProvider input(data, size);
  std::vector<int32_t> timings;
  if (input.ConsumeBool()) {
    const uint32_t expected = input.ConsumeIntegral<uint32_t>() & 0xffffffU;
    const int32_t pulse = input.ConsumeIntegralInRange<int32_t>(170, 330);
    for (int bit = 23; bit >= 0; --bit) {
      const bool one = (expected & (1U << bit)) != 0;
      timings.push_back(one ? 960 - pulse : pulse);
      timings.push_back(one ? -pulse : pulse - 960);
    }
    timings.push_back(pulse);
    timings.push_back(-4000);
    uint32_t decoded = 0, measured = 0;
    assert(rf_bridge::decode_rm433_24(timings, decoded, measured));
    assert(decoded == expected && measured == static_cast<uint32_t>(pulse));
    if (input.ConsumeBool())
      timings[input.ConsumeIntegralInRange<size_t>(0, 49)] = input.ConsumeIntegral<int32_t>();
  } else {
    while (input.remaining_bytes() >= sizeof(int32_t))
      timings.push_back(input.ConsumeIntegral<int32_t>());
  }
  uint32_t decoded = 0xfeedbeefU, measured = 0xdeadcafeU;
  if (rf_bridge::decode_rm433_24(timings, decoded, measured)) {
    assert(timings.size() == 50 && decoded <= 0xffffffU);
    assert(measured >= 170 && measured <= 330);
  } else {
    assert(decoded == 0xfeedbeefU && measured == 0xdeadcafeU);
  }
  uint32_t codes[8];
  for (auto &code : codes) code = input.ConsumeIntegral<uint32_t>();
  if (input.ConsumeBool()) codes[input.ConsumeIntegralInRange<size_t>(0, 7)] = decoded;
  const char *button = rf_bridge::rm433_button_type(decoded, codes);
  size_t first = 8;
  for (size_t i = 0; i < 8; ++i)
    if (decoded <= 0xffffffU && codes[i] == decoded) { first = i; break; }
  if (first == 8) assert(button == nullptr);
  else assert(button && std::string(button) == "button_" + std::to_string(first + 1));
  return 0;
}
