"""Exercise the actual TX input validator at the wire-format boundaries."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]

SOURCE = r"""
#include "rf_tx_validation.h"
#include <cassert>
#include <climits>
#include <cstdint>
#include <string>

int main() {
  using rf_bridge::valid_tx_request;

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
                [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I",
                 str(ROOT / "include"), str(source), "-o", str(output)],
                capture_output=True, text=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(output)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
