#include "rf_tx_validation.h"
#include <fuzzer/FuzzedDataProvider.h>
#include <algorithm>
#include <cassert>
#include <cstdint>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  FuzzedDataProvider input(data, size);
  const int protocol = input.ConsumeIntegral<int>();
  const int repeats = input.ConsumeIntegral<int>();
  const int remote = input.ConsumeIntegral<int>();
  const int channel = input.ConsumeIntegral<int>();
  const int button = input.ConsumeIntegral<int>();
  const int check = input.ConsumeIntegral<int>();
  const auto text = input.ConsumeRemainingBytesAsString();
  const bool binary = std::all_of(text.begin(), text.end(), [](char c) { return c == '0' || c == '1'; });
  const bool bounded = text.size() >= 8 && text.size() <= 64 && protocol >= 1 && protocol <= 8 && repeats >= 1 && repeats <= 10;
  assert(rf_bridge::valid_tx_request(text, protocol, repeats) == (binary && bounded));
  const bool dooya = remote >= 0 && remote < (1 << 24) && channel >= 0 && channel < 256 &&
    button >= 0 && button < 16 && check >= 0 && check < 16 && repeats >= 1 && repeats <= 10;
  assert(rf_bridge::valid_dooya_request(remote, channel, button, check, repeats) == dooya);

  // Every input also reaches valid encoding boundaries and one-byte corruption.
  std::string valid(8 + size % 57, '0');
  for (size_t i = 0; i < valid.size() && i < size; ++i) valid[i] = (data[i] & 1U) ? '1' : '0';
  assert(rf_bridge::valid_tx_request(valid, 1, 10));
  valid[size % valid.size()] = '\0';
  assert(!rf_bridge::valid_tx_request(valid, 1, 10));
  assert(rf_bridge::valid_dooya_request(static_cast<uint32_t>(remote) & 0xffffffU,
    static_cast<uint32_t>(channel) & 255U, static_cast<uint32_t>(button) & 15U,
    static_cast<uint32_t>(check) & 15U, 1));
  return 0;
}
