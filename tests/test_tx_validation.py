"""Exercise the actual TX input validator at the wire-format boundaries."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SANITIZER_FLAGS = (
    ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer", "-g", "-O1"]
    if os.environ.get("RF_CPP_SANITIZERS") == "1" else []
)

SOURCE = r"""
#include "rf_tx_validation.h"
#include <cassert>
#include <climits>
#include <cstdint>
#include <string>

int main() {
  using rf_bridge::valid_tx_request;
  using rf_bridge::valid_dooya_request;

  // Every supported width/protocol/repeat combination must remain usable.
  for (size_t width = 8; width <= 64; ++width) {
    std::string bits(width, '0');
    for (size_t bit = 0; bit < width; ++bit)
      if (bit % 3 == 0) bits[bit] = '1';
    for (int protocol = 1; protocol <= 8; ++protocol)
      for (int repeats = 1; repeats <= 10; ++repeats)
        assert(valid_tx_request(bits, protocol, repeats));
  }
  assert(valid_tx_request(std::string(64, '0'), 1, 1));
  assert(valid_tx_request(std::string(64, '1'), 8, 10));

  // A leading zero is data, not a reason to shrink the payload width.
  const std::string leading_zero = "00000001";
  assert(valid_tx_request(leading_zero, 1, 1));
  assert(leading_zero.size() == 8 && leading_zero == "00000001");

  for (size_t width = 0; width < 8; ++width)
    assert(!valid_tx_request(std::string(width, '1'), 1, 1));
  for (size_t width : {65u, 255u, 1024u, 100000u})
    assert(!valid_tx_request(std::string(width, '1'), 1, 1));
  for (int protocol : {INT_MIN, -100, -1, 0, 9, 255, INT_MAX})
    assert(!valid_tx_request("01010101", protocol, 1));
  for (int repeats : {INT_MIN, -100, -1, 0, 11, 255, INT_MAX})
    assert(!valid_tx_request("01010101", 1, repeats));

  // The receiver returns ASCII binary. Never accept whitespace, tristate x,
  // numeric prefixes, embedded NUL or high bytes as an implicit binary one.
  for (unsigned byte = 0; byte <= 255; ++byte) {
    for (size_t position : {0u, 1u, 7u, 31u, 63u}) {
      std::string bits(64, '0');
      bits[position] = static_cast<char>(byte);
      const bool is_binary = byte == static_cast<unsigned>('0') || byte == static_cast<unsigned>('1');
      assert(valid_tx_request(bits, 1, 1) == is_binary);
    }
  }
  for (const std::string bits : {"0b01010101", "0x12345678", "0101 0101", "01010101\n", "0101010x"})
    assert(!valid_tx_request(bits, 1, 1));

  // Deterministic mutations cover varied string lengths and byte offsets.
  uint32_t state = 0x6bb1101u;
  auto random = [&]() {
    state ^= state << 13; state ^= state >> 17; state ^= state << 5;
    return state;
  };
  for (unsigned iteration = 0; iteration < 10000; ++iteration) {
    const auto width = 8 + random() % 57;
    std::string bits(width, '0');
    for (auto &bit : bits) bit = random() & 1 ? '1' : '0';
    assert(valid_tx_request(bits, 1 + random() % 8, 1 + random() % 10));
    bits[random() % width] = static_cast<char>(random() % 48); // Always outside '0'/'1'.
    assert(!valid_tx_request(bits, 1, 1));
  }

  // Dooya encodes a 24-bit remote ID, 8-bit channel, and two 4-bit fields.
  // Exercise the exact narrowing boundaries and every nibble value.
  for (int remote : {0, 1, 0x7FFFFF, 0x800000, 0xFFFFFE, 0xFFFFFF})
    for (int channel : {0, 1, 127, 128, 254, 255})
      for (int button = 0; button <= 15; ++button)
        for (int check = 0; check <= 15; ++check)
          for (int repeats : {1, 10})
            assert(valid_dooya_request(remote, channel, button, check, repeats));

  for (int remote : {INT_MIN, -1, 0x1000000, INT_MAX})
    assert(!valid_dooya_request(remote, 1, 1, 1, 3));
  for (int channel : {INT_MIN, -1, 256, INT_MAX})
    assert(!valid_dooya_request(0x123456, channel, 1, 1, 3));
  for (int nibble : {INT_MIN, -1, 16, 255, INT_MAX}) {
    assert(!valid_dooya_request(0x123456, 1, nibble, 1, 3));
    assert(!valid_dooya_request(0x123456, 1, 1, nibble, 3));
  }
  for (int repeats : {INT_MIN, -1, 0, 11, INT_MAX})
    assert(!valid_dooya_request(0x123456, 1, 1, 1, repeats));

  for (unsigned iteration = 0; iteration < 10000; ++iteration) {
    const int remote = random() & 0xFFFFFF;
    const int channel = random() & 0xFF;
    const int button = random() & 0x0F;
    const int check = random() & 0x0F;
    const int repeats = 1 + random() % 10;
    assert(valid_dooya_request(remote, channel, button, check, repeats));
    assert(!valid_dooya_request(remote | 0x1000000, channel, button, check, repeats));
    assert(!valid_dooya_request(remote, channel | 0x100, button, check, repeats));
    assert(!valid_dooya_request(remote, channel, button | 0x10, check, repeats));
    assert(!valid_dooya_request(remote, channel, button, check | 0x10, repeats));
  }
}
"""


class TransmitValidationTest(unittest.TestCase):
    def test_actual_header_boundaries_and_mutations(self):
        compiler = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
        if compiler is None:
            self.skipTest("A C++17 compiler is required")
        with tempfile.TemporaryDirectory(prefix="rf-tx-validation-") as temporary:
            directory = Path(temporary)
            source = directory / "test.cpp"
            output = directory / "test"
            source.write_text(SOURCE)
            build = subprocess.run(
                [compiler, *SANITIZER_FLAGS, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I",
                 str(ROOT / "include"), str(source), "-o", str(output)],
                capture_output=True, text=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(output)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
