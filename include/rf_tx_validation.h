#pragma once

#include <string>

namespace rf_bridge {

// Validate before indexing the protocol table or parsing a 64-bit RF value.
inline bool valid_tx_request(const std::string &code, int protocol, int repeats) {
  if (code.size() < 8 || code.size() > 64 || protocol < 1 || protocol > 8 || repeats < 1 || repeats > 10)
    return false;
  for (char bit : code) {
    if (bit != '0' && bit != '1')
      return false;
  }
  return true;
}

}  // namespace rf_bridge
